from decimal import Decimal

from iafisher_foundation.prelude import *
from .base import APIWrapper
from .claude import Claude
from .gemini import Gemini
from .gpt import GPT
from .mercury import Mercury
from .model_names import *


@dataclass
class TokenCost:
    # fields based on the `llm_v3_api_requests` database table
    per_1m_input_tokens: Decimal
    per_1m_output_tokens: Decimal
    per_1m_reasoning_tokens: Optional[Decimal]
    per_1m_cache_read_tokens: Optional[Decimal]
    per_1m_cache_creation_tokens: Optional[Decimal]


@dataclass
class ModelInfo:
    constructor: Callable[[str], APIWrapper]
    family: str
    token_limit: int
    nicknames: List[str]
    tags: List[str] = dataclasses.field(default_factory=list)
    is_mock: bool = False
    token_cost: Optional[TokenCost] = None


@dataclass
class ModelFamilyInfo:
    fast_model: str
    slow_model: str


TAG_FAST = "fast"
TAG_SLOW = "slow"


MODEL_TO_INFO = {
    # https://developers.openai.com/api/docs/models/compare
    GPT_5_MINI: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=["chatgpt-5-mini", "gpt-mini"],
        tags=[TAG_FAST],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("0.05"),
            per_1m_output_tokens=Decimal("0.40"),
            per_1m_reasoning_tokens=Decimal("0.40"),
            per_1m_cache_read_tokens=Decimal("0.01"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GPT_5_NANO: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=["chatgpt-5-nano", "gpt-nano"],
        tags=[TAG_FAST],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("0.25"),
            per_1m_output_tokens=Decimal("2.00"),
            per_1m_reasoning_tokens=Decimal("2.00"),
            per_1m_cache_read_tokens=Decimal("0.03"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GPT_5_1: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=["chatgpt-5.1", "gpt-5.1", "gpt5.1"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("1.25"),
            per_1m_output_tokens=Decimal("10.00"),
            per_1m_reasoning_tokens=Decimal("10.00"),
            per_1m_cache_read_tokens=Decimal("0.13"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GPT_5_2: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=["chatgpt-5.2", "chatgpt-5", "gpt-5", "gpt-5.2", "gpt5", "gpt5.2"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("1.75"),
            per_1m_output_tokens=Decimal("14.00"),
            per_1m_reasoning_tokens=Decimal("14.00"),
            per_1m_cache_read_tokens=Decimal("0.18"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GPT_5_2_CODEX: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=[
            "gpt-5-codex",
            "gpt-5.2-codex",
            "gpt5-codex",
            "gpt5.2-codex",
            "codex",
        ],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("1.75"),
            per_1m_output_tokens=Decimal("14.00"),
            per_1m_reasoning_tokens=Decimal("14.00"),
            per_1m_cache_read_tokens=Decimal("0.18"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GPT_MOCK_WEB_SEARCH: ModelInfo(
        GPT,
        family=MODEL_FAMILY_GPT,
        token_limit=400_000,
        nicknames=[],
        is_mock=True,
    ),
    # https://platform.claude.com/docs/en/about-claude/pricing
    CLAUDE_HAIKU_4_5: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=["claude-haiku", "haiku"],
        tags=[TAG_FAST],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("1.00"),
            per_1m_output_tokens=Decimal("5.00"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.10"),
            per_1m_cache_creation_tokens=Decimal("1.25"),
        ),
    ),
    CLAUDE_OPUS_4_5: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=["claude-opus-4.5", "opus-4.5"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("5.00"),
            per_1m_output_tokens=Decimal("25.00"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.50"),
            per_1m_cache_creation_tokens=Decimal("6.25"),
        ),
    ),
    CLAUDE_OPUS_4_6: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        # Opus 4.6 supports 1 million token limit, but it's opt-in and costs extra.
        token_limit=200_000,
        nicknames=["claude-opus", "opus"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("5.00"),
            per_1m_output_tokens=Decimal("25.00"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.50"),
            per_1m_cache_creation_tokens=Decimal("6.25"),
        ),
    ),
    CLAUDE_SONNET_4_5: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=["claude-sonnet-4.5", "sonnet-4.5"],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("3.00"),
            per_1m_output_tokens=Decimal("15.00"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.30"),
            per_1m_cache_creation_tokens=Decimal("3.75"),
        ),
    ),
    CLAUDE_SONNET_4_6: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=["claude-sonnet", "sonnet"],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("3.00"),
            per_1m_output_tokens=Decimal("15.00"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.30"),
            per_1m_cache_creation_tokens=Decimal("3.75"),
        ),
    ),
    CLAUDE_MOCK_LOCAL_TOOL_USE: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=[],
        is_mock=True,
    ),
    CLAUDE_MOCK_WEB_SEARCH: ModelInfo(
        Claude,
        family=MODEL_FAMILY_CLAUDE,
        token_limit=200_000,
        nicknames=[],
        is_mock=True,
    ),
    # https://ai.google.dev/gemini-api/docs/pricing
    # TODO(2026-01): Use Gemini API to get token limit
    # https://ai.google.dev/gemini-api/docs/tokens?lang=python#context-windows
    GEMINI_2_5_FLASH: ModelInfo(
        Gemini,
        family=MODEL_FAMILY_GEMINI,
        token_limit=1_048_576,
        nicknames=["gemini-flash"],
        tags=[TAG_FAST],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("0.30"),
            per_1m_output_tokens=Decimal("2.50"),
            per_1m_reasoning_tokens=Decimal("2.50"),
            per_1m_cache_read_tokens=Decimal("0.03"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GEMINI_2_5_PRO: ModelInfo(
        Gemini,
        family=MODEL_FAMILY_GEMINI,
        token_limit=1_048_576,
        nicknames=["gemini-pro"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("1.25"),
            per_1m_output_tokens=Decimal("10.00"),
            per_1m_reasoning_tokens=Decimal("10.00"),
            per_1m_cache_read_tokens=Decimal("0.125"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GEMINI_3_PRO: ModelInfo(
        Gemini,
        family=MODEL_FAMILY_GEMINI,
        token_limit=1_048_576,
        nicknames=["gemini-3-pro", "gemini-3", "gemini3"],
        tags=[TAG_SLOW],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("2.00"),
            per_1m_output_tokens=Decimal("12.00"),
            per_1m_reasoning_tokens=Decimal("12.00"),
            per_1m_cache_read_tokens=Decimal("0.20"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
    GEMINI_MOCK_WEB_SEARCH: ModelInfo(
        Gemini,
        family=MODEL_FAMILY_GEMINI,
        token_limit=1_048_576,
        nicknames=[],
        is_mock=True,
    ),
    # https://docs.inceptionlabs.ai/get-started/models
    MERCURY_2: ModelInfo(
        Mercury,
        family=MODEL_FAMILY_MERCURY,
        token_limit=128_000,
        nicknames=["mercury"],
        token_cost=TokenCost(
            per_1m_input_tokens=Decimal("0.25"),
            per_1m_output_tokens=Decimal("0.75"),
            per_1m_reasoning_tokens=None,
            per_1m_cache_read_tokens=Decimal("0.025"),
            per_1m_cache_creation_tokens=None,
        ),
    ),
}

MODEL_FAMILY_TO_INFO = {
    MODEL_FAMILY_CLAUDE: ModelFamilyInfo(
        fast_model=CLAUDE_HAIKU_4_5, slow_model=CLAUDE_OPUS_4_6
    ),
    MODEL_FAMILY_GEMINI: ModelFamilyInfo(
        fast_model=GEMINI_2_5_FLASH, slow_model=GEMINI_3_PRO
    ),
    MODEL_FAMILY_GPT: ModelFamilyInfo(fast_model=GPT_5_MINI, slow_model=GPT_5_2),
}

NICKNAME_TO_MODEL = {
    nickname: model
    for model, model_info in MODEL_TO_INFO.items()
    for nickname in model_info.nicknames
}


def canonicalize_model_name(name: str) -> str:
    name = name.lower()
    if name in MODEL_TO_INFO:
        return name

    try:
        return NICKNAME_TO_MODEL[name]
    except KeyError:
        raise KgError("unknown model name", name=name)
