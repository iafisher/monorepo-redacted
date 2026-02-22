from app.llm2.code import Hooks
from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import sh1
from lib import githelper, llm, pdb


SYSTEM_PROMPT = """\
You are an expert code reviewer. You are presented with a Git diff that you must verify for
correctness.

Search for all of the following problems:

- Logic bugs
- Incorrect use of external libraries or interfaces
- Bad code abstractions
- Typos

You should use your tools to read files when needed for additional context.

You should concisely list all problems found, including the file name and line number, at the end.
Only list problems that occur in the diff, not existing problems in the code.

You are typically invoked non-interactively.
"""


def main(commit_hash: str, *, model: str = llm.CLAUDE_SONNET_4_6) -> None:
    root_directory = githelper.get_root(pathlib.Path("."))
    diff = sh1(f"git -C {root_directory} show {commit_hash} -U5")
    with pdb.connect() as db:
        model_response = llm.oneshot(
            db,
            diff,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            app_name="llm2::codereview",
            options=llm.InferenceOptions.normal(),
            hooks=Hooks(),
            tools=[
                llm.tools.FindFileTool(root_directory),
                llm.tools.ListFilesTool(root_directory),
                llm.tools.ReadFileTool(root_directory),
                llm.tools.SearchFileContentsTool(root_directory),
            ],
        )
        print()
        print(f"Conversation ID: {model_response.conversation_id}")
