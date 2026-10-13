from enum import StrEnum


ANY_MODEL = "any"
ANY_FAST_MODEL = "any_fast"
ANY_SLOW_MODEL = "any_slow"


class GptModel(StrEnum):
    # https://developers.openai.com/api/docs/models
    GPT_5_6_SOL = "gpt-5.6-sol"
    GPT_5_6_TERRA = "gpt-5.6-terra"
    GPT_5_6_LUNA = "gpt-5.6-luna"
    GPT_6_1_SOL = "gpt-6.1-sol"
    GPT_6_LUNA = "gpt-6-luna"
    GPT_MOCK_WEB_SEARCH = "gpt-mock-web-search"

    GPT_FAST_LATEST = GPT_6_LUNA
    GPT_5_LATEST = GPT_5_6_TERRA
    GPT_6_LATEST = GPT_6_1_SOL


class ClaudeModel(StrEnum):
    # https://platform.claude.com/docs/en/models/overview
    HAIKU_4_5 = "claude-haiku-4-5"
    HAIKU_5_5 = "claude-haiku-5-5"
    OPUS_4_5 = "claude-opus-4-5"
    OPUS_4_6 = "claude-opus-4-6"
    OPUS_4_8 = "claude-opus-4-8"
    OPUS_5 = "claude-opus-5"
    OPUS_5_5 = "claude-opus-5-5"
    SONNET_4_5 = "claude-sonnet-4-5"
    SONNET_4_6 = "claude-sonnet-4-6"
    SONNET_5 = "claude-sonnet-5"
    SONNET_5_5 = "claude-sonnet-5-5"
    FABLE_5 = "claude-fable-5"
    MOCK_LOCAL_TOOL_USE = "claude-mock-local-tool-use"
    MOCK_WEB_SEARCH = "claude-mock-web-search"

    HAIKU_LATEST = HAIKU_5_5
    OPUS_LATEST = OPUS_5
    SONNET_LATEST = SONNET_5_5


class GeminiModel(StrEnum):
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_3_8_FLASH = "gemini-3.8-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_3_PRO = "gemini-3.1-pro-preview"
    GEMINI_MOCK_WEB_SEARCH = "gemini-mock-web-search"

    GEMINI_FLASH_LATEST = GEMINI_2_5_FLASH
    GEMINI_PRO_LATEST = GEMINI_3_PRO


class MercuryModel(StrEnum):
    MERCURY_2 = "mercury-2"


MODEL_FAMILY_CLAUDE = "claude"
MODEL_FAMILY_GEMINI = "gemini"
MODEL_FAMILY_GPT = "gpt"
MODEL_FAMILY_MERCURY = "mercury"

COMPACTION_MODEL = GeminiModel.GEMINI_FLASH_LATEST
