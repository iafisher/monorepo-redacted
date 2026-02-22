import json
from typing import Iterator, Literal

import openai
import pydantic_core
import tiktoken
from openai.types.responses import ResponseStreamEvent

from iafisher_foundation.prelude import *
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
    GPT_5_1,
    GPT_5_2,
    GPT_5_2_CODEX,
    GPT_5_MINI,
    GPT_MOCK_WEB_SEARCH,
    MODEL_FAMILY_GPT,
)


MOCK_MODELS = (GPT_MOCK_WEB_SEARCH,)


class GPT(APIWrapper):
    def __init__(self, model: str) -> None:
        self.model = model
        api_key = secrets.get_or_raise("OPENAI_API_KEY")
        self.client = openai.OpenAI(api_key=api_key)

    @override
    def _query(
        self,
        messages: List[Any],
        hooks: BaseHooks,
        tools: List[BaseTool],
        *,
        options: InferenceOptions,
        system_prompt: str,
        trace: bool = False,
    ) -> ModelResponse:
        max_tokens = options.max_tokens
        temperature = options.temperature
        reasoning = options.reasoning

        if self.model == GPT_5_MINI:
            if options.strict:
                raise ModelMisconfigurationError(
                    "The model does not support custom temperature.",
                    model=self.model,
                    options=options,
                )
            else:
                temperature = 1.0
                LOG.debug(
                    "The model (%r) does not support custom temperature, falling back to %s.",
                    self.model,
                    temperature,
                )

        if reasoning is None:
            # https://developers.openai.com/api/docs/guides/latest-model/#lower-reasoning-effort
            if self.model in (GPT_5_1, GPT_5_2, GPT_5_2_CODEX):
                reasoning_effort = "none"
            else:
                reasoning_effort = "minimal"
        else:
            if reasoning.effort == "dynamic":
                if options.strict:
                    raise ModelMisconfigurationError(
                        "OpenAI models do not support dynamic reasoning.",
                        model=self.model,
                        options=options,
                    )

                reasoning_effort = "medium"
                LOG.debug(
                    "OpenAI models do not support dynamic reasoning, falling back to %r.",
                    reasoning_effort,
                )
            else:
                reasoning_effort = reasoning.effort

        if system_prompt != "":
            messages = [{"role": "developer", "content": system_prompt}] + messages

        tools_gpt = [tool.to_gpt_param() for tool in tools]
        raw_request_json = json.dumps(
            dict(
                model=self.model,
                input=messages,
                include=["reasoning.encrypted_content"],
                reasoning={"effort": reasoning_effort},
                temperature=temperature,
                max_output_tokens=max_tokens,
                tools=tools_gpt,
                store=False,
                stream=True,
            )
        )

        trace_dict = dict(stream=[])
        try:
            stream = (
                mock_stream(self.model, self.to_universal_messages(messages))
                if self.model in MOCK_MODELS
                else iter(
                    self.client.responses.create(
                        model=self.model,
                        input=messages,
                        # https://platform.openai.com/docs/guides/reasoning#encrypted-reasoning-items
                        include=["reasoning.encrypted_content"],
                        reasoning={"effort": reasoning_effort},
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        tools=tools_gpt,
                        store=False,
                        stream=True,
                    )
                )
            )

            raw_response_json: List[Any] = []
            blocks: List[Any] = []
            output_text = ""
            token_usage = TokenUsage()
            stop_reason = StopReason.OK
            for event in stream:
                trace_dict["stream"].append(event)
                raw_response_json.append(event.model_dump_json())
                if event.type == "response.output_item.done":
                    item = event.item
                    if item.type == "function_call":
                        hooks.on_tool_use_request(item.name, item.arguments)
                    elif item.type == "message":
                        for content in item.content:
                            if content.type == "refusal":
                                LOG.warning(
                                    "OpenAI returned refusal block: %r", content
                                )
                                stop_reason = StopReason.REFUSAL
                    elif item.type == "web_search_call":
                        if item.action.type == "search":
                            hooks.on_web_search([item.action.query])

                    blocks.append(item.to_dict())
                elif event.type == "response.output_text.delta" and event.delta:
                    hooks.on_text_delta(event.delta)
                elif event.type == "response.reasoning_text.delta" and event.delta:
                    hooks.on_text_delta(event.delta)
                elif event.type == "response.completed":
                    output_text = event.response.output_text
                    usage = event.response.usage
                    event.response.incomplete_details
                    if usage is not None:
                        token_usage.input_tokens = usage.input_tokens
                        token_usage.output_tokens = usage.output_tokens
                        token_usage.reasoning_tokens = (
                            usage.output_tokens_details.reasoning_tokens
                        )
                        token_usage.cache_read_tokens = (
                            usage.input_tokens_details.cached_tokens
                        )
                        token_usage.total_tokens = usage.total_tokens
                        token_usage.raw_json = usage.model_dump()
                elif event.type == "response.failed":
                    raise KgError(
                        "OpenAI API returned response.failed", response=event.response
                    )
                elif event.type == "response.incomplete":
                    LOG.warning(
                        "OpenAI API returned response.incomplete: %r", event.response
                    )
                    details = event.response.incomplete_details
                    if details is not None and details.reason == "max_output_tokens":
                        stop_reason = StopReason.MAX_TOKENS_EXCEEDED
                    else:
                        stop_reason = StopReason.UNKNOWN

            return ModelResponse(
                messages=blocks,
                output_text=output_text,
                token_usage=token_usage,
                stop_reason=stop_reason,
                raw_request_json=raw_request_json,
                raw_response_json=json.dumps(raw_response_json),
                model=self.model,
                trace=trace_dict if trace else None,
            )
        except (openai.APIError, pydantic_core.ValidationError) as e:
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

        try:
            encoder = tiktoken.encoding_for_model(self.model)
        except KeyError:
            # https://github.com/openai/tiktoken/issues/464
            default_encoding = "o200k_base"
            LOG.info(
                "failed to get tokenizer for OpenAI model %r, falling back to default encoding %r",
                self.model,
                default_encoding,
            )
            encoder = tiktoken.get_encoding(default_encoding)
        # TODO(2026-01): Probably not very accurate to just do `json.dumps` on the whole
        # messages list. Also, tools are ignored.
        return len(encoder.encode(system_prompt + " " + json.dumps(messages)))

    @override
    def _to_universal_messages(
        self, messages: List[StrDict]
    ) -> List[universal.Message]:
        r: List[universal.Message] = []
        for message in messages:
            if "content" in message:
                role = message["role"]
                for block in message["content"]:
                    if role == "assistant":
                        if "text" in block:
                            raw_annotations = block.get("annotations")
                            if raw_annotations is not None and len(raw_annotations) > 0:
                                citations = [
                                    universal.Citation(
                                        title=annotation.get("title", ""),
                                        url=annotation["url"],
                                    )
                                    for annotation in raw_annotations
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
                        else:
                            r.append(
                                universal.UnknownMessage(
                                    role="assistant", raw_json=block
                                )
                            )
                    else:
                        if "text" in block:
                            r.append(
                                universal.TextMessage(role="user", text=block["text"])
                            )
                        else:
                            r.append(
                                universal.UnknownMessage(role="user", raw_json=block)
                            )
            elif message["type"] == "reasoning":
                r.append(
                    universal.ThinkingMessage(
                        role="assistant", thinking="<GPT thinking omitted>"
                    )
                )
            elif message["type"] == "function_call":
                r.append(
                    universal.ToolUseRequest(
                        role="assistant",
                        tool_use_id=message["call_id"],
                        tool_name=message["name"],
                        tool_input=json.loads(message["arguments"]),
                    )
                )
            elif message["type"] == "function_call_output":
                r.append(
                    universal.ToolUseResponse(
                        role="user", tool_output=message["output"]
                    )
                )
            else:
                r.append(universal.UnknownMessage(role="assistant", raw_json=message))
        return r

    @override
    def _create_text_message(
        self, role: Literal["user", "assistant"], text: str
    ) -> StrDict:
        match role:
            case "user":
                content_type = "input_text"
            case "assistant":
                content_type = "output_text"

        return {
            "role": role,
            "type": "message",
            "content": [{"text": text, "type": content_type}],
        }

    @override
    def _create_tool_use_response_message(
        self, tool_use_responses: List[ToolUseResponse]
    ) -> List[StrDict]:
        return [
            {
                "type": "function_call_output",
                "call_id": tool_use_response.tool_use_id,
                "output": json.dumps(
                    {"error": tool_use_response.tool_result.error}
                    if tool_use_response.tool_result.error is not None
                    else tool_use_response.tool_result.payload
                ),
            }
            for tool_use_response in tool_use_responses
        ]

    @override
    def model_name(self) -> str:
        return self.model

    @override
    def model_family(self) -> str:
        return MODEL_FAMILY_GPT


def mock_stream(
    model: str, messages: List[universal.Message]
) -> Iterator[ResponseStreamEvent]:
    turn = load_mock_turn(model, messages)
    return IteratorWithDelay(iter(turn["stream"]))
