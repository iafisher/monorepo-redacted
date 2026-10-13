from decimal import Decimal

from iafisher.prelude import *
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


MODEL_TO_INFO: Dict[str, ModelInfo] = {}

# https://developers.openai.com/api/docs/models/compare
for model_name in GptModel:
    match model_name:
        case GptModel.GPT_5_6_SOL:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=1_050_000,
                nicknames=[],
                tags=[TAG_SLOW],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("5.00"),
                    per_1m_output_tokens=Decimal("30.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.50"),
                    per_1m_cache_creation_tokens=None,
                ),
            )
        case GptModel.GPT_5_6_TERRA:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=1_050_000,
                nicknames=["terra"],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("2.00"),
                    per_1m_output_tokens=Decimal("12.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.20"),
                    per_1m_cache_creation_tokens=None,
                ),
            )
        case GptModel.GPT_5_6_LUNA:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=1_050_000,
                nicknames=[],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("0.20"),
                    per_1m_output_tokens=Decimal("1.20"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.02"),
                    per_1m_cache_creation_tokens=None,
                ),
            )
        case GptModel.GPT_6_1_SOL:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=1_050_000,
                nicknames=["sol"],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("2.00"),
                    per_1m_output_tokens=Decimal("10.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.10"),
                    per_1m_cache_creation_tokens=Decimal("2.50"),
                ),
            )
        case GptModel.GPT_6_LUNA:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=1_050_000,
                nicknames=["luna"],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("0.10"),
                    per_1m_output_tokens=Decimal("0.50"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.01"),
                    per_1m_cache_creation_tokens=Decimal("0.125"),
                ),
            )
        case GptModel.GPT_MOCK_WEB_SEARCH:
            model_info = ModelInfo(
                GPT,
                family=MODEL_FAMILY_GPT,
                token_limit=400_000,
                nicknames=[],
                is_mock=True,
            )

    MODEL_TO_INFO[model_name] = model_info


# https://platform.claude.com/docs/en/about-claude/pricing
for model_name in ClaudeModel:
    match model_name:
        case ClaudeModel.HAIKU_4_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=200_000,
                nicknames=[],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("1.00"),
                    per_1m_output_tokens=Decimal("5.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.10"),
                    per_1m_cache_creation_tokens=Decimal("1.25"),
                ),
            )
        case ClaudeModel.HAIKU_5_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=["claude-haiku", "haiku"],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    # TODO(2026-10): these prices are up to 100,000 tokens, after that it is $0.50/$2.50
                    per_1m_input_tokens=Decimal("0.10"),
                    per_1m_output_tokens=Decimal("0.50"),
                    per_1m_reasoning_tokens=None,
                    # TODO(2026-10): these prices are up to 100,000 tokens, after that it is $0.05/$0.625
                    per_1m_cache_read_tokens=Decimal("0.01"),
                    per_1m_cache_creation_tokens=Decimal("0.125"),
                ),
            )
        case ClaudeModel.OPUS_4_5:
            model_info = ModelInfo(
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
            )
        case ClaudeModel.OPUS_4_6:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                # Opus 4.6 supports 1 million token limit, but it's opt-in and costs extra.
                token_limit=200_000,
                nicknames=["claude-opus-4.6", "opus-4.6"],
                tags=[TAG_SLOW],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("5.00"),
                    per_1m_output_tokens=Decimal("25.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.50"),
                    per_1m_cache_creation_tokens=Decimal("6.25"),
                ),
            )
        case ClaudeModel.OPUS_4_8:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=["claude-opus-4.8", "opus-4.8"],
                tags=[TAG_SLOW],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("5.00"),
                    per_1m_output_tokens=Decimal("25.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.50"),
                    per_1m_cache_creation_tokens=Decimal("10.00"),
                ),
            )
        case ClaudeModel.OPUS_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=[],
                tags=[TAG_SLOW],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("5.00"),
                    per_1m_output_tokens=Decimal("25.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.50"),
                    per_1m_cache_creation_tokens=Decimal("10.00"),
                ),
            )
        case ClaudeModel.OPUS_5_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=["claude-opus", "opus"],
                tags=[TAG_SLOW],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("4.00"),
                    per_1m_output_tokens=Decimal("20.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.20"),
                    per_1m_cache_creation_tokens=Decimal("5.00"),
                ),
            )
        case ClaudeModel.SONNET_4_5:
            model_info = ModelInfo(
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
            )
        case ClaudeModel.SONNET_4_6:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=200_000,
                nicknames=["claude-sonnet-4.6", "sonnet-4.6"],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("3.00"),
                    per_1m_output_tokens=Decimal("15.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.30"),
                    per_1m_cache_creation_tokens=Decimal("3.75"),
                ),
            )
        case ClaudeModel.SONNET_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=[],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("3.00"),
                    per_1m_output_tokens=Decimal("15.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.30"),
                    per_1m_cache_creation_tokens=Decimal("3.75"),
                ),
            )
        case ClaudeModel.SONNET_5_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=["claude-sonnet", "sonnet"],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("4.00"),
                    per_1m_output_tokens=Decimal("20.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.10"),
                    per_1m_cache_creation_tokens=Decimal("2.50"),
                ),
            )
        case ClaudeModel.FABLE_5:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=1_000_000,
                nicknames=["claude-fable", "fable"],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("10.00"),
                    per_1m_output_tokens=Decimal("50.00"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("1.00"),
                    per_1m_cache_creation_tokens=Decimal("12.50"),
                ),
            )
        case ClaudeModel.MOCK_LOCAL_TOOL_USE:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=200_000,
                nicknames=[],
                is_mock=True,
            )
        case ClaudeModel.MOCK_WEB_SEARCH:
            model_info = ModelInfo(
                Claude,
                family=MODEL_FAMILY_CLAUDE,
                token_limit=200_000,
                nicknames=[],
                is_mock=True,
            )

    MODEL_TO_INFO[model_name] = model_info

for model_name in GeminiModel:
    # https://ai.google.dev/gemini-api/docs/pricing
    # TODO(2026-01): Use Gemini API to get token limit
    # https://ai.google.dev/gemini-api/docs/tokens?lang=python#context-windows
    match model_name:
        case GeminiModel.GEMINI_2_5_FLASH:
            model_info = ModelInfo(
                Gemini,
                family=MODEL_FAMILY_GEMINI,
                token_limit=1_048_576,
                nicknames=[],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    per_1m_input_tokens=Decimal("0.30"),
                    per_1m_output_tokens=Decimal("2.50"),
                    per_1m_reasoning_tokens=Decimal("2.50"),
                    per_1m_cache_read_tokens=Decimal("0.03"),
                    per_1m_cache_creation_tokens=None,
                ),
            )
        case GeminiModel.GEMINI_3_8_FLASH:
            model_info = ModelInfo(
                Gemini,
                family=MODEL_FAMILY_GEMINI,
                token_limit=1_048_576,
                nicknames=["gemini-flash"],
                tags=[TAG_FAST],
                token_cost=TokenCost(
                    # Prices increase on 2027-01-01. These prices are through 2026-12-31.
                    per_1m_input_tokens=Decimal("0.75"),
                    per_1m_output_tokens=Decimal("3.75"),
                    per_1m_reasoning_tokens=None,
                    per_1m_cache_read_tokens=Decimal("0.075"),
                    per_1m_cache_creation_tokens=None,
                ),
            )
        case GeminiModel.GEMINI_2_5_PRO:
            model_info = ModelInfo(
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
            )
        case GeminiModel.GEMINI_3_PRO:
            model_info = ModelInfo(
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
            )
        case GeminiModel.GEMINI_MOCK_WEB_SEARCH:
            model_info = ModelInfo(
                Gemini,
                family=MODEL_FAMILY_GEMINI,
                token_limit=1_048_576,
                nicknames=[],
                is_mock=True,
            )

    MODEL_TO_INFO[model_name] = model_info


# https://docs.inceptionlabs.ai/get-started/models
for model_name in MercuryModel:
    match model_name:
        case MERCURY_2:
            model_info = ModelInfo(
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
            )

    MODEL_TO_INFO[model_name] = model_info

MODEL_FAMILY_TO_INFO = {
    MODEL_FAMILY_CLAUDE: ModelFamilyInfo(
        fast_model=ClaudeModel.HAIKU_LATEST, slow_model=ClaudeModel.OPUS_LATEST
    ),
    MODEL_FAMILY_GEMINI: ModelFamilyInfo(
        fast_model=GeminiModel.GEMINI_FLASH_LATEST,
        slow_model=GeminiModel.GEMINI_PRO_LATEST,
    ),
    MODEL_FAMILY_GPT: ModelFamilyInfo(
        fast_model=GptModel.GPT_FAST_LATEST, slow_model=GptModel.GPT_5_LATEST
    ),
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
