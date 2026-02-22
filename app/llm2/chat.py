from app.llm2 import chatloop
from app.llm2.common import flag_to_reasoning_v3
from iafisher_foundation.prelude import *
from lib import llm

from .redacted import *


SYSTEM_PROMPT = f"""\
You are a helpful assistant interacting with a user via a chat interface on the
command line.

Some basic information about the user:

{BASIC_INFORMATION}

Your responses should be concise unless otherwise requested.
"""


def main(
    *,
    model: str = llm.CLAUDE_SONNET_4_6,
    max_tokens: int = llm.MAX_TOKENS,
    temperature: float = 1.0,
    reasoning: str = "medium",
    resume: Optional[int] = None,
) -> None:
    reasoning_v3 = flag_to_reasoning_v3(reasoning)  # type: ignore
    resume_conversation_id = resume

    options = llm.InferenceOptions(
        max_tokens=max_tokens, temperature=temperature, reasoning=reasoning_v3
    )
    chatloop.loop(
        app_subname="code",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        hooks=llm.PrintTextHook(print_thoughts=True),
        tools=[llm.tools.WebSearchTool()],
        resume_conversation_id=resume_conversation_id,
        options=options,
    )
