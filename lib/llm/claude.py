import json
import time
from copy import deepcopy
from typing import Iterator, Literal, Self

import anthropic
import pydantic_core
from anthropic import types as anthropic_types
from anthropic._types import omit as anthropic_omit

from iafisher.prelude import *
from lib import secrets
from . import universal
from .base import (
    APIWrapper,
    BaseHooks,
    BaseTool,
    InferenceOptions,
    ModelMisconfigurationError,
    ModelResponse,
    ModelResponseError,
    StopReason,
    ToolUseResponse,
)
from .common import IteratorWithDelay, TokenUsage, load_mock_turn
from .model_names import (
    ClaudeModel,
    MODEL_FAMILY_CLAUDE,
)


MOCK_MODELS = (ClaudeModel.MOCK_LOCAL_TOOL_USE, ClaudeModel.MOCK_WEB_SEARCH)


class Claude(APIWrapper):
    def __init__(self, model: str) -> None:
        self.model = ClaudeModel(model)
        api_key = secrets.get_or_raise("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key)

    @override
    def _query(
        self,
        messages: List[StrDict],
        hooks: BaseHooks,
        tools: List[BaseTool],
        *,
        options: InferenceOptions,
        system_prompt: str,
        trace: bool,
    ) -> ModelResponse:
        max_tokens = options.max_tokens
        temperature = options.temperature

        thinking, output_config = _create_thinking_param(options, self.model)

        if options.caching:
            messages = messages[:]
            last_message = deepcopy(messages[-1])
            last_message["content"][-1]["cache_control"] = {"type": "ephemeral"}
            messages[-1] = last_message

        tools_claude = [tool.to_claude_param() for tool in tools]
        trace_dict = dict(stream=[], final_message=None)
        raw_request_json = json.dumps(
            dict(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking=thinking,
                output_config=output_config,
                system=system_prompt,
                tools=tools_claude,
                messages=messages,
            )
        )
        try:
            stream_impl: anthropic.MessageStreamManager = (
                MockStream(self.model, self.to_universal_messages(messages))
                if self.model in MOCK_MODELS
                else self.client.messages.stream(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking=thinking,
                    output_config=opt_or(output_config, anthropic_omit),
                    system=system_prompt,
                    tools=tools_claude,
                    messages=messages,  # type: ignore
                )
            )
            with stream_impl as stream:
                raw_response_json: List[Any] = []
                content_blocks: List[StrDict] = []
                output_text_builder: List[str] = []
                for block in stream:
                    trace_dict["stream"].append(block)  # type: ignore
                    # `warnings=False`: http://llm/conversation/78
                    raw_response_json.append(block.model_dump_json(warnings=False))
                    match block.type:
                        case "content_block_delta":
                            if block.delta.type == "text_delta":
                                hooks.on_text_delta(block.delta.text)
                                output_text_builder.append(block.delta.text)
                            elif block.delta.type == "thinking_delta":
                                hooks.on_thinking_delta(block.delta.thinking)
                        case "content_block_stop":
                            content = block.content_block
                            match content.type:
                                case "tool_use":
                                    hooks.on_tool_use_request(
                                        content.name, content.input
                                    )
                                case "server_tool_use":
                                    if content.name == "web_search":
                                        hooks.on_web_search([content.input["query"]])  # type: ignore
                                case _:
                                    pass

                            # `warnings=False`: http://llm/conversation/78
                            content_blocks.append(
                                block.content_block.to_dict(warnings=False)
                            )
                        case _:
                            pass

                final_message = stream.get_final_message()
                trace_dict["final_message"] = final_message  # type: ignore
                usage = final_message.usage
                token_usage = TokenUsage(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_input_tokens,
                    cache_creation_tokens=usage.cache_creation_input_tokens,
                    total_tokens=usage.input_tokens
                    + usage.output_tokens
                    + (usage.cache_read_input_tokens or 0)
                    + (usage.cache_creation_input_tokens or 0),
                    # `warnings=False`: http://llm/conversation/78
                    raw_json=usage.model_dump(warnings=False),
                )

                if final_message.stop_reason in ("end_turn", "tool_use"):
                    stop_reason = StopReason.OK
                elif final_message.stop_reason == "max_tokens":
                    stop_reason = StopReason.MAX_TOKENS_EXCEEDED
                elif final_message.stop_reason == "refusal":
                    stop_reason = StopReason.REFUSAL
                else:
                    LOG.warning(
                        "Claude returned unknown stop reason: %r",
                        final_message.stop_reason,
                    )
                    stop_reason = StopReason.UNKNOWN

                return ModelResponse(
                    [{"role": "assistant", "content": content_blocks}],
                    output_text="".join(output_text_builder),
                    token_usage=token_usage,
                    stop_reason=stop_reason,
                    raw_request_json=raw_request_json,
                    raw_response_json=json.dumps(raw_response_json),
                    model=self.model,
                    trace=trace_dict if trace else None,
                )
        except (anthropic.AnthropicError, pydantic_core.ValidationError) as e:
            raise ModelResponseError(
                raw_request_json=raw_request_json, original_exception=e
            )

    @override
    def count_tokens(
        self,
        messages: List[StrDict],
        *,
        system_prompt: str = "",
        tools: List[BaseTool] = [],
    ) -> int:
        if self.model in MOCK_MODELS or len(messages) == 0:
            return 0

        token_count = self.client.messages.count_tokens(
            messages=messages,  # type: ignore
            model=self.model,
            system=system_prompt,
            tools=[tool.to_claude_param() for tool in tools],
        )
        return token_count.input_tokens

    @override
    def _to_universal_messages(
        self, messages: List[StrDict]
    ) -> List[universal.Message]:
        r: List[universal.Message] = []
        for message in messages:
            role = message["role"]
            for block in message["content"]:
                if role == "assistant":
                    if "text" in block:
                        raw_citations = block.get("citations")
                        if raw_citations is not None and len(raw_citations) > 0:
                            citations = [
                                universal.Citation(
                                    title=citation.get("title", ""), url=citation["url"]
                                )
                                for citation in raw_citations
                            ]
                        else:
                            citations = []

                        r.append(
                            universal.TextMessage(
                                role="assistant",
                                text=block["text"],
                                citations=citations,
                            )
                        )
                    elif "thinking" in block:
                        r.append(
                            universal.ThinkingMessage(
                                role="assistant", thinking=block["thinking"]
                            )
                        )
                    elif block["type"] == "tool_use":
                        r.append(
                            universal.ToolUseRequest(
                                role="assistant",
                                tool_use_id=block["id"],
                                tool_name=block["name"],
                                tool_input=block["input"],
                            )
                        )
                    else:
                        r.append(
                            universal.UnknownMessage(role="assistant", raw_json=block)
                        )
                else:
                    if "text" in block:
                        r.append(universal.TextMessage(role="user", text=block["text"]))
                    elif block["type"] == "tool_result":
                        r.append(
                            universal.ToolUseResponse(
                                role="user", tool_output=json.dumps(block["content"])
                            )
                        )
                    else:
                        r.append(universal.UnknownMessage(role="user", raw_json=block))
        return r

    @override
    def _create_text_message(
        self, role: Literal["user", "assistant"], text: str
    ) -> StrDict:
        return {"role": role, "content": [{"type": "text", "text": text}]}

    @override
    def _create_tool_use_response_message(
        self, tool_use_responses: List[ToolUseResponse]
    ) -> List[StrDict]:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_response.tool_use_id,
                        "content": json.dumps(
                            tool_use_response.tool_result.payload
                            if tool_use_response.tool_result.error is None
                            else {"error": tool_use_response.tool_result.error}
                        ),
                    }
                    for tool_use_response in tool_use_responses
                ],
            }
        ]

    @override
    def model_name(self) -> str:
        return self.model

    @override
    def model_family(self) -> str:
        return MODEL_FAMILY_CLAUDE


def _create_thinking_param(
    options: InferenceOptions, model: ClaudeModel
) -> Tuple[Any, Any]:
    # https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking#supported-models
    # https://platform.claude.com/docs/en/build-with-claude/extended-thinking
    match model:
        case ClaudeModel.HAIKU_4_5 | ClaudeModel.OPUS_4_5 | ClaudeModel.SONNET_4_5:
            return _create_thinking_param_legacy(options, model), None
        case (
            ClaudeModel.FABLE_5
            | ClaudeModel.OPUS_4_6
            | ClaudeModel.OPUS_4_8
            | ClaudeModel.SONNET_4_6
            | ClaudeModel.SONNET_5
        ):
            return _create_thinking_param_adaptive(options)
        case ClaudeModel.MOCK_LOCAL_TOOL_USE | ClaudeModel.MOCK_WEB_SEARCH:
            return None, None
        case _:
            impossible()


def _create_thinking_param_adaptive(options: InferenceOptions) -> Tuple[Any, Any]:
    if options.reasoning is None:
        return anthropic_types.ThinkingConfigDisabledParam(type="disabled"), None
    else:
        match options.reasoning.effort:
            case "dynamic":
                output_config = None
            case "high":
                output_config = anthropic_types.OutputConfigParam(effort="high")
            case "medium":
                output_config = anthropic_types.OutputConfigParam(effort="medium")
            case "low":
                output_config = anthropic_types.OutputConfigParam(effort="low")

        return (
            anthropic_types.ThinkingConfigAdaptiveParam(type="adaptive"),
            output_config,
        )


def _create_thinking_param_legacy(options: InferenceOptions, model: str) -> Any:
    reasoning = options.reasoning
    temperature = options.temperature
    max_tokens = options.max_tokens

    if reasoning is not None:
        if temperature != 1.0:
            if options.strict:
                raise ModelMisconfigurationError(
                    "Claude does not support custom temperature when reasoning is enabled.",
                    model=model,
                    options=options,
                )
            else:
                temperature = 1.0
                LOG.debug(
                    "Claude does not support custom temperature when reasoning is enabled, falling back to %s.",
                    temperature,
                )

        if reasoning.effort == "dynamic":
            if options.strict:
                raise ModelMisconfigurationError(
                    "Claude does not support dynamic reasoning.",
                    model=model,
                    options=options,
                )
            effort = "medium"
            LOG.debug(
                "Claude does not support dynamic reasoning, falling back to %r.",
                effort,
            )
        else:
            effort = reasoning.effort

        if reasoning.summary is False:
            if options.strict:
                raise ModelMisconfigurationError(
                    "`reasoning.summary` is False, but Claude does not support turning off reasoning summaries",
                    model=model,
                    options=options,
                )

        # https://github.com/BerriAI/litellm/blob/v1.79.3-stable/litellm/constants.py#L75
        if effort == "low":
            # NOTE: This is the minimum possible value of `budget_tokens`.
            budget_tokens = 1024
        elif effort == "medium":
            budget_tokens = 2048
        else:
            budget_tokens = 4096

        if max_tokens <= budget_tokens:
            if options.strict:
                raise ModelMisconfigurationError(
                    "reasoning was enabled for Claude but the max tokens is too low for the reasoning effort",
                    max_tokens=max_tokens,
                    inferred_budget_tokens=budget_tokens,
                    reasoning=reasoning,
                )
            else:
                max_tokens = budget_tokens
                LOG.debug(
                    "max_tokens for Claude was too low for desired reasoning effort (%r), bumped to %d.",
                    effort,
                    max_tokens,
                )

        return anthropic_types.ThinkingConfigEnabledParam(
            type="enabled", budget_tokens=budget_tokens
        )
    else:
        return anthropic_types.ThinkingConfigDisabledParam(type="disabled")


class MockStream:
    _model: str
    _messages: List[universal.Message]
    _chunks: List[Any]
    _iter: Iterator[Any]

    def __init__(self, model: str, messages: List[universal.Message]) -> None:
        turn = load_mock_turn(model, messages)
        self._model = model
        self._chunks = turn["stream"]
        self._final_message = turn["final_message"]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def __iter__(self) -> Any:
        time.sleep(0.3)
        return IteratorWithDelay(iter(self._chunks))

    def get_final_message(self) -> Any:
        return self._final_message
