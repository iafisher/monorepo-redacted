import random
from decimal import Decimal
from typing import Literal, Self

from iafisher_foundation import colors, timehelper
from iafisher_foundation.prelude import *
from lib import pdb

from . import storage, universal
from .base import APIWrapper, BaseHooks, BaseTool, InferenceOptions, ModelResponse
from .common import TokenUsage
from .model_info import (
    MODEL_TO_INFO,
    TAG_FAST,
    TAG_SLOW,
    ModelInfo,
    TokenCost,
    canonicalize_model_name,
)
from .model_names import ANY_FAST_MODEL, ANY_MODEL, ANY_SLOW_MODEL


class PrintTextHook(BaseHooks):
    _print_thoughts: bool
    _last_printed: Literal["", "text", "thought"]

    def __init__(self, *, print_thoughts: bool = False) -> None:
        self._print_thoughts = print_thoughts
        self._last_printed = ""

    @override
    def on_text_delta(self, text: str) -> None:
        if self._last_printed == "thought":
            print()
            print()

        print(text, end="", flush=True)

    @override
    def on_thinking_delta(self, text: str) -> None:
        if not self._print_thoughts:
            return

        if self._last_printed == "text":
            print()
            print()

        colors.print(colors.gray(text), end="", flush=True)


class Conversation:
    def __init__(
        self,
        *,
        api: APIWrapper,
        conversation_id: int,
        messages: List[StrDict],
        system_prompt: str,
    ) -> None:
        """
        Don't call this directly. Use `start` or `resume` instead.
        """
        self._api = api
        self.model_info = MODEL_TO_INFO[self._api.model_name()]
        self.conversation_id = conversation_id
        self.messages = messages
        self.system_prompt = system_prompt

    @classmethod
    def start(
        cls, db: pdb.Connection, *, model: str, app_name: str, system_prompt: str
    ) -> Self:
        api = _create_api(model)
        now = timehelper.now()
        messages: List[StrDict] = []
        conversation_id = storage.create_conversation(
            db,
            model=api.model_name(),
            app_name=app_name,
            system_prompt=system_prompt,
            messages=messages,
            now=now,
        )
        return cls(
            api=api,
            conversation_id=conversation_id,
            messages=messages,
            system_prompt=system_prompt,
        )

    @classmethod
    def resume(cls, db: pdb.Connection, conversation_id: int) -> Self:
        db_conversation = storage.fetch_conversation(db, conversation_id)
        api = _create_api(db_conversation.model)
        return cls(
            api=api,
            conversation_id=db_conversation.conversation_id,
            messages=db_conversation.messages,
            system_prompt=db_conversation.system_prompt,
        )

    @classmethod
    def fork(cls, db: pdb.Connection, conversation_id: int) -> Self:
        now = timehelper.now()
        db_conversation = storage.fork_conversation(db, conversation_id, now=now)
        api = _create_api(db_conversation.model)
        return cls(
            api=api,
            conversation_id=db_conversation.conversation_id,
            messages=db_conversation.messages,
            system_prompt=db_conversation.system_prompt,
        )

    def switch_model(self, db: pdb.Connection, new_model: str) -> None:
        api = _create_api(new_model)
        messages = api.from_universal_messages(self.universal_messages())
        self.__init__(
            api=api,
            conversation_id=self.conversation_id,
            messages=messages,
            system_prompt=self.system_prompt,
        )
        storage.update_conversation_and_model(
            db,
            self.conversation_id,
            messages,
            model=api.model_name(),
            now=timehelper.now(),
        )

    def prompt(
        self,
        db: pdb.Connection,
        text: str,
        *,
        hooks: BaseHooks,
        options: InferenceOptions,
        tools: List[BaseTool],
        trace: bool = False,
        override_system_prompt: Optional[str] = None,
    ) -> ModelResponse:
        self.enqueue(db, text)
        return self._api.one_turn(
            db,
            self.conversation_id,
            self.messages,
            hooks=hooks,
            tools=tools,
            options=options,
            system_prompt=(
                override_system_prompt
                if override_system_prompt is not None
                else self.system_prompt
            ),
            trace=trace,
        )

    def reprompt(
        self,
        db: pdb.Connection,
        *,
        hooks: BaseHooks,
        options: InferenceOptions,
        tools: List[BaseTool],
        trace: bool = False,
    ) -> ModelResponse:
        return self._api.one_turn(
            db,
            self.conversation_id,
            self.messages,
            hooks=hooks,
            tools=tools,
            options=options,
            system_prompt=self.system_prompt,
            trace=trace,
        )

    def enqueue(self, db: pdb.Connection, text: str) -> None:
        self.messages.append(self._api._create_text_message("user", text))
        now = timehelper.now()
        storage.update_conversation(db, self.conversation_id, self.messages, now=now)

    def last_token_usage(self, db: pdb.Connection) -> TokenUsage:
        return storage.fetch_last_token_usage(db, self.conversation_id)

    def model_name(self) -> str:
        return self._api.model_name()

    def count_tokens(self) -> int:
        return self._api.count_tokens(self.messages, system_prompt=self.system_prompt)

    def universal_messages(self) -> List[universal.Message]:
        return self._api.to_universal_messages(self.messages)


def count_tokens(model: str, messages: List[StrDict]) -> int:
    api = _create_api(model)
    return api.count_tokens(messages)


@dataclass
class CostPerRequest:
    model: str
    total_input_tokens: int
    total_output_tokens: int
    total_reasoning_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    token_cost: TokenCost

    def input_token_cost(self) -> Decimal:
        return self._cost(self.total_input_tokens, self.token_cost.per_1m_input_tokens)

    def output_token_cost(self) -> Decimal:
        return self._cost(
            self.total_output_tokens, self.token_cost.per_1m_output_tokens
        )

    def reasoning_token_cost(self) -> Decimal:
        return self._cost(
            self.total_reasoning_tokens, self.token_cost.per_1m_reasoning_tokens
        )

    def cache_read_token_cost(self) -> Decimal:
        return self._cost(
            self.total_cache_read_tokens, self.token_cost.per_1m_cache_read_tokens
        )

    def cache_creation_token_cost(self) -> Decimal:
        return self._cost(
            self.total_cache_creation_tokens,
            self.token_cost.per_1m_cache_creation_tokens,
        )

    def _cost(self, token_count: int, cost_per_1m: Optional[Decimal]) -> Decimal:
        if cost_per_1m is None:
            return Decimal("0")
        else:
            return Decimal(token_count) / 1_000_000 * cost_per_1m

    def total_cost(self) -> Decimal:
        return (
            self.input_token_cost()
            + self.output_token_cost()
            + self.reasoning_token_cost()
            + self.cache_read_token_cost()
            + self.cache_creation_token_cost()
        )


@dataclass
class CostBreakdown:
    requests: List[CostPerRequest]


def estimate_conversation_cost(
    db: pdb.Connection, conversation_id: int
) -> Optional[CostBreakdown]:
    rows = db.fetch_all(
        """
        SELECT
          model,
          COALESCE(input_tokens, 0) AS totaL_input_tokens,
          COALESCE(output_tokens, 0) AS total_output_tokens,
          COALESCE(reasoning_tokens, 0) AS total_reasoning_tokens,
          COALESCE(cache_read_tokens, 0) AS total_cache_read_tokens,
          COALESCE(cache_creation_tokens, 0) AS total_cache_creation_tokens
        FROM
          llm_v3_api_requests
        WHERE
          conversation_id = %(conversation_id)s
        """,
        dict(conversation_id=conversation_id),
        t=pdb.tuple_row,
    )

    requests: List[CostPerRequest] = []
    for row in rows:
        (
            model,
            total_input_tokens,
            total_output_tokens,
            total_reasoning_tokens,
            total_cache_read_tokens,
            total_cache_creation_tokens,
        ) = row

        model_info = MODEL_TO_INFO[canonicalize_model_name(model)]
        if model_info.token_cost is None:
            return None

        requests.append(
            CostPerRequest(
                model=model,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_reasoning_tokens=total_reasoning_tokens,
                total_cache_read_tokens=total_cache_read_tokens,
                total_cache_creation_tokens=total_cache_creation_tokens,
                token_cost=model_info.token_cost,
            )
        )

    return CostBreakdown(requests=requests)


def oneshot(
    db: pdb.Connection,
    prompt: str,
    *,
    model: str,
    system_prompt: str,
    app_name: str,
    options: InferenceOptions,
    hooks: BaseHooks = BaseHooks(),
    tools: List[BaseTool] = [],
    trace: bool = False,
) -> ModelResponse:
    api = _create_api(model)
    conversation_id = storage.create_conversation(
        db,
        model=api.model_name(),
        app_name=app_name,
        system_prompt=system_prompt,
        messages=[],
        now=timehelper.now(),
    )
    messages = [api._create_text_message("user", prompt)]
    storage.update_conversation(db, conversation_id, messages, now=timehelper.now())
    return api.one_turn(
        db,
        conversation_id,
        messages,
        hooks=hooks,
        options=options,
        system_prompt=system_prompt,
        tools=tools,
        trace=trace,
    )


def _create_api(name: str) -> APIWrapper:
    def _pick_from_candidates(candidates: List[Tuple[str, ModelInfo]]) -> APIWrapper:
        model_name, info = random.choice(candidates)
        return info.constructor(model_name)

    if name == ANY_MODEL:
        return _pick_from_candidates(list(MODEL_TO_INFO.items()))
    elif name == ANY_FAST_MODEL:
        candidates = [
            (model_name, model_info)
            for model_name, model_info in MODEL_TO_INFO.items()
            if TAG_FAST in model_info.tags
        ]
        return _pick_from_candidates(candidates)
    elif name == ANY_SLOW_MODEL:
        candidates = [
            (model_name, model_info)
            for model_name, model_info in MODEL_TO_INFO.items()
            if TAG_SLOW in model_info.tags
        ]
        return _pick_from_candidates(candidates)
    else:
        canonical_name = canonicalize_model_name(name)
        info = MODEL_TO_INFO[canonical_name]
        return info.constructor(canonical_name)


def get_token_limit(model: str) -> int:
    canonical_name = canonicalize_model_name(model)
    info = MODEL_TO_INFO[canonical_name]
    return info.token_limit
