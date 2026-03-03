from abc import ABC, abstractmethod
from typing import Literal, Self

from anthropic import types as anthropic_types
from openai.types import responses as openai_types

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import pdb

from . import storage, universal
from .common import TokenUsage


class StopReason(enum.Enum):
    OK = enum.auto()
    REFUSAL = enum.auto()
    MAX_TOKENS_EXCEEDED = enum.auto()
    UNKNOWN = enum.auto()


ReasoningEffort = Union[
    Literal["dynamic"],
    Literal["low"],
    Literal["medium"],
    Literal["high"],
]


@dataclass
class Reasoning:
    effort: ReasoningEffort
    summary: bool


# LiteLLM uses 4096 by default, but there doesn't seem to be much downside to increasing it.
# https://github.com/BerriAI/litellm/blob/v1.79.3-stable/litellm/constants.py#L33
MAX_TOKENS = 16000
MAX_TOKENS_FAST = 4096
MAX_TOKENS_SLOW = 32000


@dataclass
class InferenceOptions:
    max_tokens: int
    temperature: float
    reasoning: Optional[Reasoning]
    # If `strict` is true, an exception will be raised if the model does not support the
    # exact requested settings. Otherwise, the closest equivalent settings will be used.
    strict: bool = False
    caching: bool = True

    @classmethod
    def fast(cls) -> Self:
        return cls(max_tokens=MAX_TOKENS_FAST, temperature=1.0, reasoning=None)

    @classmethod
    def normal(cls) -> Self:
        return cls(
            max_tokens=MAX_TOKENS,
            temperature=1.0,
            reasoning=Reasoning(effort="dynamic", summary=True),
        )

    @classmethod
    def slow(cls) -> Self:
        return cls(
            max_tokens=MAX_TOKENS_SLOW,
            temperature=1.0,
            reasoning=Reasoning(effort="high", summary=True),
        )


class BaseTool(ABC):
    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def get_plain_description(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def get_input_schema(cls) -> StrDict:
        pass

    @classmethod
    @abstractmethod
    def get_output_schema(cls) -> StrDict:
        pass

    @abstractmethod
    def call(self, params: Any) -> Any:
        pass

    def get_param(self, params: Any, name: str) -> Any:
        try:
            return params[name]
        except KeyError:
            raise ToolError(f"{name!r} is not a valid parameter of this tool")

    # TODO(2026-02): `to_claude_param` should be defined on the `Claude` class, etc.
    #
    # One tricky thing is that these methods are overloaded on the `WebSearchTool` which is
    # special because it is a built-in tool.

    def to_claude_param(self) -> anthropic_types.ToolParam:
        return anthropic_types.ToolParam(
            name=self.get_name(),
            description=self.get_plain_description(),
            input_schema=self.get_input_schema(),
        )

    def to_gemini_param(self) -> StrDict:
        return dict(
            function_declarations=[
                dict(
                    name=self.get_name(),
                    description=self.get_plain_description(),
                    parameters=self.get_input_schema(),
                    response=self.get_output_schema(),
                )
            ]
        )

    def to_gpt_param(self) -> openai_types.ToolParam:
        return openai_types.FunctionToolParam(
            type="function",
            name=self.get_name(),
            description=self.get_plain_description(),
            parameters={
                **self.get_input_schema(),
                # This is required by the OpenAI API.
                "additionalProperties": False,
            },
            strict=False,
            # When `strict=True`, the OpenAI API does not allow tools to have optional
            # parameters. (Other providers allow this.)
        )

    def to_mercury_param(self) -> StrDict:
        return {
            "type": "function",
            "function": {
                "name": self.get_name(),
                "description": self.get_plain_description(),
                "parameters": self.get_input_schema(),
            },
        }


class ToolError(Exception):
    """
    Use this class to raise 'expected' exceptions (as opposed to bugs in the tool implementation.)
    """


@dataclass
class ToolResult:
    payload: Any
    error: Optional[str]


@dataclass
class ToolUseResponse:
    tool_name: str
    tool_use_id: str
    tool_result: ToolResult


class BaseHooks(ABC):
    def on_text_delta(self, _text: str) -> None:
        pass

    def on_tool_use_request(self, _tool_name: str, _tool_input: Any) -> None:
        pass

    def on_tool_internal_error(self, _exc: Exception) -> None:
        pass

    def on_tool_use_response(self, _tool_name: str, _tool_result: ToolResult) -> None:
        pass

    def on_thinking_delta(self, _text: str) -> None:
        pass

    def on_web_search(self, _queries: List[str]) -> None:
        pass

    def on_api_request(self) -> None:
        pass


class LoggingHooks(BaseHooks):
    @override
    def on_tool_use_request(self, tool_name: str, _tool_input: Any) -> None:
        LOG.info("LLM hooks: on_tool_use_request: %s", tool_name)

    @override
    def on_web_search(self, _queries: List[str]) -> None:
        LOG.info("LLM hooks: on_web_search")

    @override
    def on_api_request(self) -> None:
        LOG.info("LLM hooks: on_api_request")


@dataclass
class ModelResponse:
    messages: List[StrDict]
    output_text: str
    token_usage: TokenUsage
    stop_reason: StopReason
    raw_request_json: str
    raw_response_json: str
    # `model` is useful because users of the `oneshot` API might pass in a model class rather than
    # a specific model, so they need to know what model they are actually using.
    model: str
    conversation_id: int = -1
    request_ids: List[int] = dataclasses.field(default_factory=list)
    # A trace contains the exact Python objects returned by the API so that they can be replayed later.
    # Unlike `raw_response_json`, it may be a Python object, not necessarily a dictionary. The format of
    # the object (even the top-level structure) is model-specific.
    trace: Any = None


class ModelResponseError(KgError):
    raw_request_json: str

    def __init__(
        self, *, raw_request_json: str, original_exception: Union[Exception, str]
    ) -> None:
        self.raw_request_json = raw_request_json
        super().__init__(
            "The model API returned an error.", message=str(original_exception)
        )


class ModelStopReasonError(KgError):
    def __init__(self, response: ModelResponse) -> None:
        super().__init__("The model stopped content generation.", response=response)


class ModelMisconfigurationError(KgError):
    pass


class APIWrapper(ABC):
    def one_turn(
        self,
        db: pdb.Connection,
        conversation_id: int,
        messages: List[StrDict],
        *,
        hooks: BaseHooks,
        tools: List[BaseTool],
        options: InferenceOptions,
        raise_for_stop_reason: bool = True,
        system_prompt: str = "",
        trace: bool = False,
    ) -> ModelResponse:
        tools_dict = {tool.get_name(): tool for tool in tools}
        request_ids: List[int] = []
        full_trace = dict(turns=[])
        while True:
            hooks.on_api_request()
            try:
                model_response = self._query(
                    messages,
                    hooks,
                    tools,
                    options=options,
                    system_prompt=system_prompt,
                    trace=trace,
                )
            except ModelResponseError as e:
                storage.create_api_request(
                    db,
                    conversation_id,
                    model=self.model_name(),
                    request_json=e.raw_request_json,
                    response_json="{}",
                    is_error=True,
                    token_usage=TokenUsage(),
                    now=timehelper.now(),
                )
                raise
            except Exception as e:
                raise KgError("The model API returned an error.", exception=e)

            if trace:
                full_trace["turns"].append(model_response.trace)
            request_id = storage.create_api_request(
                db,
                conversation_id,
                model=self.model_name(),
                request_json=model_response.raw_request_json,
                response_json=model_response.raw_response_json,
                is_error=False,
                token_usage=model_response.token_usage,
                now=timehelper.now(),
            )
            request_ids.append(request_id)

            if model_response.stop_reason != StopReason.OK:
                if raise_for_stop_reason:
                    raise ModelStopReasonError(model_response)
                else:
                    break

            tool_use_responses: List[ToolUseResponse] = []
            # We have to be careful to avoid adding tool-use requests until the corresponding
            # tool-use responses are ready, because the Claude API (and likely others) will not
            # accept requests without responses. This goes for both the in-memory `messages` list,
            # and what we store to the database. So:
            #
            #   - Accumulate messages in `messages_to_append` and add them to `messages` all at
            #     once.
            #   - Don't store anything to the database until all requests are satisfied.
            #
            # We have to be paranoid here because the user could press Ctrl+C and interrupt this
            # code at any time.
            messages_to_append: List[StrDict] = []
            for message in model_response.messages:
                messages_to_append.append(message)
                for tool_use_request in self._to_universal_messages([message]):
                    if not isinstance(tool_use_request, universal.ToolUseRequest):
                        continue

                    tool_result = self._invoke_tool(
                        tools_dict,
                        tool_use_request.tool_name,
                        tool_use_request.tool_input,
                        hooks=hooks,
                    )
                    tool_use_responses.append(
                        ToolUseResponse(
                            tool_use_id=tool_use_request.tool_use_id,
                            tool_name=tool_use_request.tool_name,
                            tool_result=tool_result,
                        )
                    )

            if len(tool_use_responses) > 0:
                # See comment above. I _think_ that `extend` can never be interrupted by a
                # `KeyboardInterrupt`, so this should be safe.
                messages.extend(
                    messages_to_append
                    + self._create_tool_use_response_message(tool_use_responses)
                )
            else:
                messages.extend(messages_to_append)

            storage.update_conversation(
                db, conversation_id, messages, now=timehelper.now()
            )

            if len(tool_use_responses) == 0:
                break

        model_response.conversation_id = conversation_id
        model_response.request_ids = request_ids
        if trace:
            model_response.trace = full_trace
        return model_response

    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def model_family(self) -> str:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def count_tokens(
        self,
        messages: List[StrDict],
        *,
        system_prompt: str = "",
        tools: List[BaseTool] = [],
    ) -> int:
        pass

    def to_universal_messages(self, messages: List[StrDict]) -> List[universal.Message]:
        return _merge_text_messages(self._to_universal_messages(messages))

    @abstractmethod
    def _to_universal_messages(
        self, messages: List[StrDict]
    ) -> List[universal.Message]:
        pass

    def from_universal_messages(
        self, messages: List[universal.Message]
    ) -> List[StrDict]:
        r: List[StrDict] = []
        for message in messages:
            match message:
                case universal.TextMessage():
                    r.append(self._create_text_message(message.role, message.text))
                case universal.ThinkingMessage():
                    r.append(
                        self._create_text_message(
                            message.role, f"Thinking: {message.thinking}"
                        )
                    )
                case universal.ToolUseRequest():
                    r.append(
                        self._create_text_message(
                            message.role,
                            f"Tool use request (tool: {message.tool_name}): {message.tool_input}",
                        )
                    )
                case universal.ToolUseResponse():
                    r.append(
                        self._create_text_message(
                            message.role, f"Tool use response: {message.tool_output}"
                        )
                    )
                case _:
                    # TODO(2026-02): Define the `universal.Message` type in such a way that this
                    # case is not necessary, e.g. as a union.
                    pass
        return r

    @abstractmethod
    def _create_text_message(
        self, role: Literal["user", "assistant"], text: str
    ) -> StrDict:
        pass

    @abstractmethod
    def _create_tool_use_response_message(
        self, tool_use_responses: List[ToolUseResponse]
    ) -> List[StrDict]:
        # This has a slightly awkward type signature to support all models:
        #
        #   - Claude and Gemini require all tool-use responses to be in the
        #     same top-level message.
        #   - GPT requires each tool-use response to be its own top-level
        #     message.
        #
        pass

    def _invoke_tool(
        self,
        tools_dict: Dict[str, BaseTool],
        tool_name: str,
        tool_input: Any,
        *,
        hooks: BaseHooks,
    ) -> ToolResult:
        try:
            tool = tools_dict[tool_name]
        except KeyError:
            result = ToolResult(
                payload=None, error=f"No tool named {tool_name!r} is available."
            )
        else:
            try:
                tool_output = tool.call(tool_input)
            except ToolError as e:
                result = ToolResult(payload=None, error=str(e))
            except Exception as e:
                hooks.on_tool_internal_error(e)
                result = ToolResult(
                    payload=None, error=f"The tool encountered an internal error: {e}"
                )
            else:
                result = ToolResult(payload=tool_output, error=None)

        hooks.on_tool_use_response(tool_name, result)
        return result


def _merge_text_messages(messages: List[universal.Message]) -> List[universal.Message]:
    r: List[universal.Message] = []
    for message in messages:
        if len(r) == 0:
            r.append(message)
        else:
            if (
                isinstance(message, universal.TextMessage)
                and isinstance(r[-1], universal.TextMessage)
                and message.role == r[-1].role
            ):
                r[-1].merge_in_place(message)
            else:
                r.append(message)
    return r
