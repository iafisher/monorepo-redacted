import json
from typing import Annotated, Literal

from app.llm2 import chatloop, common
from iafisher_foundation import colors, timehelper
from iafisher_foundation.prelude import *
from lib import command, githelper, llm


SYSTEM_PROMPT = """\
You are a senior software engineer LLM working on a code repository.

You are given tools that allow you to explore and manipulate the repository.

For tasks that require multiple steps, write out a plan using the scratchpad tool first.
At the end, check the scratchpad to make sure you've done everything you planned to.
You don't need to use the scratchpad for small tasks.

At the end of each turn, you can give a brief summary of what you did, in a paragraph or
less. Don't give a lengthy summary with headers and lists.

The user is an experienced software engineer. You are interacting with them via a chat
loop on the command line. In general the user will be supervising you closely, so if you
are confused or unsure about something, you should ask the user.

You do not have access to the shell. If you need a shell command to be run, you can ask
the user.

The user may edit files while you are running, so do not be surprised if changes that you
did not make appear. Do not undo such changes; if you think they are wrong, ask the user
about it.
"""


class Hooks(llm.BaseHooks):
    _just_printed_what: Literal["", "text", "log", "thought"]

    def __init__(self) -> None:
        self._just_printed_what = ""

    @override
    def on_text_delta(self, text: str) -> None:
        if self._just_printed_what in ("log", "thought"):
            print()

        print(text, end="", flush=True)
        self._just_printed_what = "text"

    @override
    def on_api_request(self) -> None:
        self._log("API request sent.")

    @override
    def on_thinking_delta(self, text: str) -> None:
        if self._just_printed_what in ("log", "text"):
            print()

        print(colors.gray(text), end="", flush=True)
        self._just_printed_what = "thought"

    @override
    def on_tool_use_request(self, tool_name: str, tool_input: Any) -> None:
        self._log(f"The model requested to use the {tool_name!r} tool.")
        if isinstance(tool_input, str):
            # For OpenAI models, the tool input is already serialized to JSON.
            tool_input_str = tool_input
        else:
            tool_input_str = json.dumps(tool_input)
        colors.print(colors.gray(tool_input_str))

    @override
    def on_tool_use_response(self, tool_name: str, tool_result: llm.ToolResult) -> None:
        self._log(f"The {tool_name!r} tool returned a response.")
        if tool_result.error:
            colors.print(colors.red(tool_result.error))

    def _log(self, message: str) -> None:
        if self._just_printed_what in ("text", "thought"):
            print()

        now_str = timehelper.now().strftime("%H:%M:%S")
        colors.print(f"{colors.cyan('[' + now_str + ']')} {message}")
        self._just_printed_what = "log"


def main(
    *,
    root_directory: Annotated[
        Optional[pathlib.Path], command.Extra(name="-directory")
    ] = None,
    model: str = llm.CLAUDE_SONNET_4_6,
    auto_approve: bool = False,
    bash: bool = False,
    resume_conversation_id: Annotated[
        Optional[int],
        command.Extra(name="-resume", help="resume a conversation with this ID"),
    ] = None,
) -> None:
    if root_directory is None:
        try:
            root_directory = githelper.get_root(pathlib.Path("."))
        except Exception:
            root_directory = pathlib.Path(".").resolve()

        LOG.debug("inferred root directory to be %s", root_directory)

    scratchpad = llm.tools.Scratchpad()
    tools: List[llm.BaseTool] = [
        # file retrieval tools
        llm.tools.FindFileTool(root_directory),
        llm.tools.ListFilesTool(root_directory),
        llm.tools.ReadFileTool(root_directory),
        llm.tools.SearchFileContentsTool(root_directory),
        # file manipulation tools
        llm.tools.CreateEmptyDirectory(root_directory, auto_approve=auto_approve),
        llm.tools.CreateFileTool(root_directory, auto_approve=auto_approve),
        llm.tools.ReplaceInFileTool(root_directory, auto_approve=auto_approve),
        # scratchpad tools
        llm.tools.GetScratchpadTool(scratchpad),
        llm.tools.SetScratchpadTool(scratchpad),
    ]

    # Gemini can't handle web search alongside custom tools:
    # https://github.com/google/adk-python/issues/53
    if not model.startswith("gemini-"):
        tools.append(llm.tools.WebSearchTool())

    if bash:
        tools.append(llm.tools.BashCommandTool(root_directory))

    system_prompt = SYSTEM_PROMPT + common.get_agents_file(root_directory)
    chatloop.loop(
        app_subname="code",
        system_prompt=system_prompt,
        model=model,
        hooks=Hooks(),
        tools=tools,
        resume_conversation_id=resume_conversation_id,
        options=llm.InferenceOptions.normal(),
    )
