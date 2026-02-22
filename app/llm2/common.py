from typing import Literal

from iafisher_foundation.prelude import *
from lib import llm


def flag_to_reasoning_v3(
    flag: Union[llm.ReasoningEffort, Literal["none"]]
) -> Optional[llm.Reasoning]:
    if flag == "none":
        return None
    else:
        return llm.Reasoning(effort=flag, summary=True)


def get_agents_file(directory: pathlib.Path) -> str:
    candidates = [
        directory / "AGENTS.md",
        directory / "agents.md",
        directory / "tools" / "config" / "agents.md",
        directory / "config" / "agents.md",
    ]

    for candidate in candidates:
        if candidate.exists():
            LOG.debug("agents.md file found at %s", candidate)
            return "\n" + candidate.read_text()

    LOG.debug("no agents.md file in %s", directory)
    return ""
