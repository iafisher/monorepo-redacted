import json
from typing import Iterator, Literal

import pydantic_core
from google import genai
from google.genai import errors as google_errors, types as google_types

from iafisher_foundation.prelude import *
from lib import iterhelper, secrets
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
from .model_names import GEMINI_2_5_PRO, GEMINI_MOCK_WEB_SEARCH, MODEL_FAMILY_GEMINI

MOCK_MODELS = (GEMINI_MOCK_WEB_SEARCH,)


class Gemini(APIWrapper):
    # https://ai.google.dev/api/generate-content#FinishReason
    REFUSAL_FINISH_REASONS = [
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
    ]

    OK_FINISH_REASONS = ["FINISH_REASON_UNSPECIFIED", "STOP"]
    INVALID_REQUEST_FINISH_REASONS = ["MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL"]
    MAX_TOKENS_FINISH_REASON = "MAX_TOKENS"

    def __init__(self, model: str) -> None:
        self.model = model
        api_key = secrets.get_or_raise("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)

    @override
    def _query(
        self,
        messages: Any,
        hooks: BaseHooks,
        tools: List[BaseTool],
        *,
        options: InferenceOptions,
        system_prompt: str,
        trace: bool,
    ) -> ModelResponse:
        config = self._make_config(options, tools, system_prompt)
        request_messages = [_format_for_api(message) for message in messages]
        raw_request_json = json.dumps(
            dict(model=self.model, contents=request_messages, config=config)
        )

        trace_dict = dict(stream=[])
        try:
            response = (
                mock_stream(self.model, self.to_universal_messages(messages))
                if self.model in MOCK_MODELS
                else self.client.models.generate_content_stream(  # type: ignore[reportUnknownReturnType]
                    model=self.model, contents=request_messages, config=config
                )
            )

            raw_response_json: List[Any] = []
            new_messages: List[StrDict] = []
            output_text_builder: List[str] = []
            token_usage = TokenUsage()
            stop_reason = StopReason.OK
            for chunk in response:
                trace_dict["stream"].append(chunk)
                raw_response_json.append(chunk.model_dump_json())
                if (
                    chunk.candidates is None
                    or len(chunk.candidates) == 0
                    or chunk.candidates[0].content is None
                ):
                    continue

                if len(chunk.candidates) > 1:
                    LOG.warning(
                        "Gemini API returned more than 1 candidate; only considering the first. (model=%r)",
                        self.model,
                    )

                finish_reason = chunk.candidates[0].finish_reason
                if finish_reason in self.REFUSAL_FINISH_REASONS:
                    stop_reason = StopReason.REFUSAL
                elif finish_reason in self.INVALID_REQUEST_FINISH_REASONS:
                    LOG.warning("Gemini API returned finish_reason=%r", finish_reason)
                elif finish_reason == self.MAX_TOKENS_FINISH_REASON:
                    stop_reason = StopReason.MAX_TOKENS_EXCEEDED
                elif (
                    finish_reason is not None
                    and finish_reason not in self.OK_FINISH_REASONS
                ):
                    LOG.warning(
                        "Gemini returned unknown stop reason: %r", finish_reason
                    )
                    stop_reason = StopReason.UNKNOWN

                parts = chunk.candidates[0].content.parts
                if parts is None:
                    continue

                for part in parts:
                    if part.text is not None:
                        if part.thought:
                            hooks.on_thinking_delta(part.text)
                        else:
                            hooks.on_text_delta(part.text)
                            output_text_builder.append(part.text)
                    elif part.function_call is not None:
                        if part.function_call.name is None:
                            raise KgError(
                                "Gemini API returned a 'function_call' block where 'name' is None",
                                block=part,
                            )

                        hooks.on_tool_use_request(
                            part.function_call.name, part.function_call.args
                        )

                if chunk.usage_metadata is not None:
                    token_usage.input_tokens = chunk.usage_metadata.prompt_token_count
                    token_usage.output_tokens = (
                        chunk.usage_metadata.candidates_token_count
                    )
                    token_usage.reasoning_tokens = (
                        chunk.usage_metadata.thoughts_token_count
                    )
                    token_usage.cache_read_tokens = (
                        chunk.usage_metadata.cached_content_token_count
                    )
                    token_usage.total_tokens = chunk.usage_metadata.total_token_count
                    token_usage.raw_json = chunk.usage_metadata.to_json_dict()

                new_messages.append(chunk.candidates[0].to_json_dict())

            return ModelResponse(
                new_messages,
                output_text="".join(output_text_builder),
                token_usage=token_usage,
                stop_reason=stop_reason,
                raw_request_json=raw_request_json,
                raw_response_json=json.dumps(raw_response_json),
                model=self.model,
                trace=trace_dict if trace else None,
            )
        except (google_errors.APIError, pydantic_core.ValidationError) as e:
            raise ModelResponseError(
                raw_request_json=raw_request_json, original_exception=e
            )

    def _make_config(
        self, options: InferenceOptions, tools: List[BaseTool], system_prompt: str
    ) -> google_types.GenerateContentConfigDict:
        max_tokens = options.max_tokens
        temperature = options.temperature
        reasoning = options.reasoning

        if self.model.startswith("gemini-3-"):
            is_gemini_3 = True
        else:
            is_gemini_3 = False

        if is_gemini_3:
            if reasoning is None:
                if options.strict:
                    raise ModelMisconfigurationError(
                        "`reasoning` parameter was None, but reasoning cannot be turned off "
                        + "for Gemini 3 models.",
                        model=self.model,
                        options=options,
                    )

                thinking_config = None
            else:
                if reasoning.effort == "low":
                    thinking_level = google_types.ThinkingLevel.LOW
                elif reasoning.effort == "high":
                    thinking_level = google_types.ThinkingLevel.HIGH
                else:
                    if options.strict:
                        raise ModelMisconfigurationError(
                            "Gemini 3 does not support the desired reasoning level.",
                            model=self.model,
                            options=options,
                        )

                    thinking_level = google_types.ThinkingLevel.HIGH
                    LOG.debug(
                        "Gemini 3 does not support %r reasoning, falling back to %r.",
                        reasoning.effort,
                        thinking_level,
                    )

                thinking_config = google_types.ThinkingConfigDict(
                    include_thoughts=reasoning.summary, thinking_level=thinking_level
                )
        else:
            if reasoning is None:
                if self.model == GEMINI_2_5_PRO:
                    if options.strict:
                        raise ModelMisconfigurationError(
                            "`reasoning` parameter was None, but reasoning cannot be turned off "
                            + "for Gemini 2.5 Pro.",
                            model=self.model,
                            options=options,
                        )
                    thinking_config = None
                else:
                    thinking_config = google_types.ThinkingConfigDict(thinking_budget=0)
            else:
                # https://ai.google.dev/gemini-api/docs/thinking#set-budget
                # low = 1/3 of max, medium = 2/3 of max, high = max
                # note that the ranges differ for different models
                if reasoning.effort == "dynamic":
                    thinking_budget = -1
                elif reasoning.effort == "low":
                    if self.model == GEMINI_2_5_PRO:
                        thinking_budget = 10900
                    else:
                        thinking_budget = 8192
                elif reasoning.effort == "medium":
                    if self.model == GEMINI_2_5_PRO:
                        thinking_budget = 16384
                    else:
                        thinking_budget = 12288
                else:
                    if self.model == GEMINI_2_5_PRO:
                        thinking_budget = 32768
                    else:
                        thinking_budget = 24576

                thinking_config = google_types.ThinkingConfigDict(
                    include_thoughts=reasoning.summary, thinking_budget=thinking_budget
                )

        return google_types.GenerateContentConfigDict(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt,
            thinking_config=thinking_config,
            tools=[tool.to_gemini_param() for tool in tools],
        )

    @override
    def count_tokens(
        self,
        messages: List[StrDict],
        system_prompt: str = "",
        tools: List[BaseTool] = [],
    ) -> int:
        if self.model in MOCK_MODELS or len(messages) == 0:
            return 0

        response = self.client.models.count_tokens(  # type: ignore
            model=self.model,
            contents=[_format_for_api(message) for message in messages],
            # Passing system prompt and tools is currently broken in the Gemini API:
            # https://github.com/googleapis/python-genai/issues/432
            # config=dict(
            #     system_instruction=system_prompt,
            #     tools=[tool.to_gemini_param() for tool in tools],
            # ),
        )
        return response.total_tokens or -1

    @override
    def _to_universal_messages(
        self, messages: List[StrDict]
    ) -> List[universal.Message]:
        r: List[universal.Message] = []
        for raw_message in messages:
            message = _format_for_api(raw_message)

            raw_citations = raw_message.get("grounding_metadata", {}).get(
                "grounding_chunks"
            )
            if raw_citations is not None and len(raw_citations) > 0:
                citations = [
                    universal.Citation(
                        title=data["web"].get("title", ""), url=data["web"]["uri"]
                    )
                    for data in raw_citations
                    if "web" in data
                ]
            else:
                citations = []

            role = message["role"]
            for part, is_last in iterhelper.iter_is_last(message["parts"]):
                if role == "model":
                    if "text" in part:
                        r.append(
                            universal.TextMessage(
                                role="assistant",
                                text=part["text"],
                                citations=citations if is_last else [],
                            )
                        )
                    elif "function_call" in part:
                        function_call = part["function_call"]
                        r.append(
                            universal.ToolUseRequest(
                                role="assistant",
                                tool_use_id="",
                                tool_name=function_call["name"],
                                tool_input=function_call["args"],
                            )
                        )
                    else:
                        r.append(
                            universal.UnknownMessage(role="assistant", raw_json=part)
                        )
                else:
                    if "text" in part:
                        r.append(universal.TextMessage(role="user", text=part["text"]))
                    elif "function_response" in part:
                        function_response = part["function_response"]
                        r.append(
                            universal.ToolUseResponse(
                                role="user",
                                tool_output=json.dumps(function_response["response"]),
                            )
                        )
                    else:
                        r.append(universal.UnknownMessage(role="user", raw_json=part))
        return r

    @override
    def _create_text_message(
        self, role: Literal["user", "assistant"], text: str
    ) -> StrDict:
        match role:
            case "user":
                gemini_role = role
            case "assistant":
                gemini_role = "model"

        return {"role": gemini_role, "parts": [{"text": text}]}

    @override
    def _create_tool_use_response_message(
        self, tool_use_responses: List[ToolUseResponse]
    ) -> List[StrDict]:
        return [
            {
                "role": "user",
                "parts": [
                    {
                        "function_response": {
                            "name": tool_use_response.tool_name,
                            "response": (
                                {"output": tool_use_response.tool_result.payload}
                                if tool_use_response.tool_result.error is None
                                else {"error": tool_use_response.tool_result.error}
                            ),
                        }
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
        return MODEL_FAMILY_GEMINI


def _format_for_api(message: StrDict) -> StrDict:
    # The Gemini API only expects the `content` part of the message to be passed back to it, but
    # other parts of the message include important information that we want to preserve, e.g.,
    # web search results and citations.
    return message["content"] if "content" in message else message


def mock_stream(
    model: str, messages: List[universal.Message]
) -> Iterator[google_types.GenerateContentResponse]:
    turn = load_mock_turn(model, messages)
    return IteratorWithDelay(iter(turn["stream"]))
