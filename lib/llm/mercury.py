import json
from typing import Literal

from iafisher_foundation.prelude import *
from lib import kghttp, secrets

from . import universal
from .base import (
    APIWrapper,
    BaseHooks,
    BaseTool,
    InferenceOptions,
    ModelResponse,
    StopReason,
    TokenUsage,
    ToolUseResponse,
)
from .model_names import MODEL_FAMILY_MERCURY


class Mercury(APIWrapper):
    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = secrets.get("INCEPTION_AI_API_KEY")

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
        # TODO(2026-02): implement tracing

        stop_reason = None

        if system_prompt != "":
            messages = [{"role": "system", "content": system_prompt}] + messages

        # https://docs.inceptionlabs.ai/get-started/models
        if options.reasoning is not None:
            match options.reasoning.effort:
                case "low":
                    reasoning_effort = "low"
                case "medium" | "dynamic":
                    reasoning_effort = "medium"
                case "high":
                    reasoning_effort = "high"

            reasoning_summary = options.reasoning.summary
        else:
            reasoning_effort = "instant"
            reasoning_summary = False

        # temperature must be in range [0.5, 1]
        temperature = max(options.temperature, 0.5)

        tools_mercury = [tool.to_mercury_param() for tool in tools]
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": options.max_tokens,
            "tools": tools_mercury,
            "reasoning_effort": reasoning_effort,
            "reasoning_summary": reasoning_summary,
            "temperature": temperature,
        }
        response = kghttp.post(
            "https://api.inceptionlabs.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        ).json()

        thinking = response.get("reasoning_summary", {}).get("content", "")
        if thinking != "" and thinking is not None:
            hooks.on_thinking_delta(thinking)

        choice = response["choices"][0]
        response_message = choice["message"]
        output_text = response_message["content"]
        if output_text != "":
            hooks.on_text_delta(output_text)

        tool_calls = response_message.get("tool_calls")
        if tool_calls is not None:
            for tool_call in tool_calls:
                hooks.on_tool_use_request(
                    tool_call["function"]["name"],
                    json.loads(tool_call["function"]["arguments"]),
                )

        finish_reason = choice["finish_reason"]
        if finish_reason is not None:
            if finish_reason == "stop" or finish_reason == "tool_calls":
                stop_reason = StopReason.OK
            else:
                stop_reason = StopReason.UNKNOWN

        usage = response["usage"]
        return ModelResponse(
            messages=[response_message],
            output_text=output_text,
            token_usage=TokenUsage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                reasoning_tokens=usage.get("reasoning_tokens"),
                cache_read_tokens=usage.get("cached_input_tokens"),
                total_tokens=usage.get("total_tokens"),
                raw_json=usage,
            ),
            stop_reason=(stop_reason or StopReason.UNKNOWN),
            raw_request_json=json.dumps(payload),
            raw_response_json=json.dumps(response),
            model=self.model,
        )

    # TODO(2026-02): Tool use wasn't working for me in streaming mode.
    # def _query_streaming(
    #     self,
    #     messages: List[Any],
    #     hooks: BaseHooks,
    #     tools: List[BaseTool],
    #     *,
    #     options: InferenceOptions,
    #     system_prompt: str,
    #     trace: bool = False,
    # ) -> ModelResponse:
    #     # TODO(2026-02): implement tracing
    #     # TODO(2026-02): respect inference options

    #     output_text_builder: List[str] = []
    #     raw_response_json: List[Any] = []
    #     stop_reason = None

    #     if system_prompt != "":
    #         messages = [{"role": "system", "content": system_prompt}] + messages

    #     tools_mercury = [tool.to_mercury_param() for tool in tools]
    #     payload = {
    #         "model": self.model,
    #         "messages": messages,
    #         "max_tokens": options.max_tokens,
    #         "stream": True,
    #         "stream_options": {"include_usage": True},
    #         "tools": tools_mercury,
    #     }
    #     # TODO(2026-02): Use kghttp once it supports streaming.
    #     with requests.post(
    #         "https://api.inceptionlabs.ai/v1/chat/completions",
    #         headers={"Authorization": f"Bearer {self.api_key}"},
    #         json=payload,
    #         stream=True,
    #     ) as r:
    #         r.raise_for_status()
    #         for chunk_bytes in r.iter_lines(8192):
    #             chunk_str = chunk_bytes.decode("utf8")
    #             prefix = "data: "
    #             if not chunk_str.startswith(prefix):
    #                 continue

    #             chunk_str = chunk_str[len(prefix) :]
    #             if chunk_str == "[DONE]":
    #                 continue

    #             data = json.loads(chunk_str)
    #             print(data)
    #             raw_response_json.append(data)
    #             if "error" in data:
    #                 raise ModelResponseError(
    #                     raw_request_json=json.dumps(payload),
    #                     original_exception=data["error"],
    #                 )

    #             choice = data["choices"][0]
    #             if "delta" in choice:
    #                 delta = choice["delta"]
    #                 if "content" in delta:
    #                     text = delta["content"]
    #                     hooks.on_text_delta(text)
    #                     output_text_builder.append(text)

    #             finish_reason = choice["finish_reason"]
    #             if finish_reason is not None:
    #                 if finish_reason == "stop" or finish_reason == "tool_calls":
    #                     stop_reason = StopReason.OK
    #                 else:
    #                     stop_reason = StopReason.UNKNOWN

    #     output_text = "".join(output_text_builder)
    #     return ModelResponse(
    #         messages=[{"role": "assistant", "content": [{"text": output_text}]}],
    #         output_text=output_text,
    #         # TODO(2026-02): Parse token usage.
    #         token_usage=TokenUsage(),
    #         stop_reason=(stop_reason or StopReason.UNKNOWN),
    #         raw_request_json=json.dumps(payload),
    #         raw_response_json=json.dumps(raw_response_json),
    #         model=self.model,
    #     )

    @override
    def count_tokens(
        self,
        messages: List[StrDict],
        *,
        system_prompt: str = "",
        tools: List[BaseTool] = [],
    ) -> int:
        raise NotImplementedError

    @override
    def _to_universal_messages(
        self, messages: List[StrDict]
    ) -> List[universal.Message]:
        r: List[universal.Message] = []
        for message in messages:
            role = message["role"]
            text = message.get("content", "")
            if role == "tool" and message.get("tool_call_id") is not None:
                r.append(
                    universal.ToolUseResponse(
                        role="user", tool_output=message["content"]
                    )
                )
            else:
                if len(text) > 0:
                    if role == "assistant":
                        r.append(
                            universal.TextMessage(
                                role="assistant", text=message["content"]
                            )
                        )
                    else:
                        r.append(
                            universal.TextMessage(role="user", text=message["content"])
                        )

                tool_calls = message.get("tool_calls")
                if tool_calls is not None:
                    for tool_call in tool_calls:
                        r.append(
                            universal.ToolUseRequest(
                                role="assistant",
                                tool_use_id=tool_call["id"],
                                tool_name=tool_call["function"]["name"],
                                tool_input=json.loads(
                                    tool_call["function"]["arguments"]
                                ),
                            )
                        )

        return r

    @override
    def _create_tool_use_response_message(
        self, tool_use_responses: List[ToolUseResponse]
    ) -> List[StrDict]:
        return [
            {
                "role": "tool",
                "tool_call_id": tool_use_response.tool_use_id,
                "content": json.dumps(
                    {"error": tool_use_response.tool_result.error}
                    if tool_use_response.tool_result.error is not None
                    else tool_use_response.tool_result.payload
                ),
            }
            for tool_use_response in tool_use_responses
        ]

    @override
    def _create_text_message(
        self, role: Literal["user", "assistant"], text: str
    ) -> StrDict:
        return {"role": role, "content": text}

    @override
    def model_name(self) -> str:
        return self.model

    @override
    def model_family(self) -> str:
        return MODEL_FAMILY_MERCURY


# == EXAMPLE RESPONSE ==
# Note that this response is from the chat completions API, while this module uses the streaming API.
#
# {
#     "id": "chatcmpl-0a05f2be-f694-41b6-aeb3-d6cfeba75925",
#     "object": "chat.completion",
#     "created": 1772299254,
#     "model": "mercury-2",
#     "choices": [
#         {
#             "index": 0,
#             "message": {
#                 "role": "assistant",
#                 "content": "South Africa has three capital cities:\n\n- **Pretoria** – the administrative (executive) capital  \n- **Cape Town** – the legislative capital, where the Parliament meets  \n- **Bloemfontein** – the judicial capital, the the Supreme Court of Appeal is located.",
#                 "tool_calls": None,
#                 "tool_call_id": None,
#             },
#             "finish_reason": "stop",
#         }
#     ],
#     "usage": {
#         "prompt_tokens": 184,
#         "reasoning_tokens": 63,
#         "completion_tokens": 56,
#         "total_tokens": 303,
#         "cached_input_tokens": 163,
#     },
#     "warning": None,
#     "reasoning_summary": {"content": None, "status": "unavailable"},
# }
#
# Example tool call:
#
# {
#     "id": "chatcmpl-362c0068-f93f-4a04-9c28-36b453a182a1",
#     "object": "chat.completion",
#     "created": 1772307965,
#     "model": "mercury-2",
#     "choices": [
#         {
#             "index": 0,
#             "message": {
#                 "role": "assistant",
#                 "content": "",
#                 "tool_calls": [
#                     {
#                         "index": 0,
#                         "id": "chatcmpl-tool-a3ebb8833e67f2c6",
#                         "type": "function",
#                         "function": {
#                             "name": "read_file",
#                             "arguments": '{\n  "path": "README.md"\n}',
#                         },
#                     }
#                 ],
#                 "tool_call_id": None,
#             },
#             "finish_reason": "tool_calls",
#         }
#     ],
#     "usage": {
#         "prompt_tokens": 406,
#         "reasoning_tokens": 42,
#         "completion_tokens": 10,
#         "total_tokens": 458,
#         "cached_input_tokens": 178,
#     },
#     "warning": None,
#     "reasoning_summary": {"content": None, "status": "unavailable"},
# }
