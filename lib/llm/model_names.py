from enum import StrEnum


ANY_MODEL = "any"
ANY_FAST_MODEL = "any_fast"
ANY_SLOW_MODEL = "any_slow"


class GptModel(StrEnum):
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_4_NANO = "gpt-5.4-nano"
    GPT_5_1 = "gpt-5.1"
    GPT_5_2 = "gpt-5.2"
    GPT_5_2_CODEX = "gpt-5.2-codex"
    GPT_5_5 = "gpt-5.5"
    GPT_5_6_SOL = "gpt-5.6-sol"
    GPT_5_6_TERRA = "gpt-5.6-terra"
    GPT_5_6_LUNA = "gpt-5.6-luna"
    GPT_MOCK_WEB_SEARCH = "gpt-mock-web-search"

    GPT_MINI_LATEST = GPT_5_4_MINI
    GPT_NANO_LATEST = GPT_5_4_NANO
    GPT_5_LATEST = GPT_5_6_TERRA


class ClaudeModel(StrEnum):
    HAIKU_4_5 = "claude-haiku-4-5"
    OPUS_4_5 = "claude-opus-4-5"
    OPUS_4_6 = "claude-opus-4-6"
    OPUS_4_8 = "claude-opus-4-8"
    SONNET_4_5 = "claude-sonnet-4-5"
    SONNET_4_6 = "claude-sonnet-4-6"
    SONNET_5 = "claude-sonnet-5"
    FABLE_5 = "claude-fable-5"
    MOCK_LOCAL_TOOL_USE = "claude-mock-local-tool-use"
    MOCK_WEB_SEARCH = "claude-mock-web-search"

    HAIKU_LATEST = HAIKU_4_5
    OPUS_LATEST = OPUS_4_8
    SONNET_LATEST = SONNET_4_6


class GeminiModel(StrEnum):
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
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
