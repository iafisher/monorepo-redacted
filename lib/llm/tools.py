import subprocess

from anthropic import types as anthropic_types
from openai.types import responses as openai_types

from iafisher_foundation import colors
from iafisher_foundation.prelude import *
from lib import githelper
from .base import BaseTool, ToolError


class FindFileTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "find_file"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Find a file in the repository by name."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                name=dict(type="string", description="The name of the file to find.")
            ),
            required=["name"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="array",
            items=dict(type="string"),
            description="A list of matching file paths, relative to the repository root.",
        )

    def __init__(self, root_directory: pathlib.Path) -> None:
        self.root_directory = root_directory

    @override
    def call(self, params: Any) -> Any:
        name = self.get_param(params, "name")
        proc = subprocess.run(
            ["fd", name],
            cwd=self.root_directory,
            text=True,
            capture_output=True,
            timeout=10.0,
        )

        if proc.returncode != 0:
            raise ToolError(
                f"The `fd` command exited with an error code of {proc.returncode}."
            )

        return proc.stdout.splitlines()


class CreateFileTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "create_file"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Create a new file in the repository."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                path=dict(
                    type="string",
                    description="The path to create, relative to the root of the repository.",
                ),
                new_contents=dict(
                    type="string", description="The new contents of the file."
                ),
            ),
            required=["path", "new_contents"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    def __init__(self, root_directory: pathlib.Path, *, auto_approve: bool = False):
        self.root_directory = root_directory
        self.auto_approve = auto_approve

    @override
    def call(self, params: Any) -> Any:
        path = self.root_directory / pathlib.Path(self.get_param(params, "path"))
        new_contents = self.get_param(params, "new_contents")

        if not path.is_relative_to(self.root_directory):
            raise ToolError("The given path is not a relative path.")

        if path.exists():
            raise ToolError("The given path already exists.")

        if not path.parent.exists():
            raise ToolError("The given path's parent directory does not exist.")

        relpath = path.relative_to(self.root_directory)
        if relpath.parts[0] in (".git", ".venv"):
            raise ToolError("You may not create paths in that directory.")

        if not self.auto_approve:
            confirm_model_action(f"create {relpath}", new_contents)

        path.write_text(new_contents)


class CreateEmptyDirectory(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "create_empty_directory"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Create a new empty directory in the repository."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                path=dict(
                    type="string",
                    description="The path to create, relative to the root of the repository. "
                    + "Intermediate empty directories will also be created.",
                ),
            ),
            required=["path"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    def __init__(self, root_directory: pathlib.Path, *, auto_approve: bool = False):
        self.root_directory = root_directory
        self.auto_approve = auto_approve

    @override
    def call(self, params: Any) -> Any:
        path = self.root_directory / pathlib.Path(self.get_param(params, "path"))

        if not path.is_relative_to(self.root_directory):
            raise ToolError("The given path is not a relative path.")

        if path.exists():
            raise ToolError("The given path already exists.")

        relpath = path.relative_to(self.root_directory)
        if relpath.parts[0] in (".git", ".venv"):
            raise ToolError("You may not create paths in that directory.")

        if not self.auto_approve:
            confirm_model_action(f"create the directory {relpath}")

        path.mkdir(parents=True)


class ReplaceInFileTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "replace_in_file"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Replace old text with new text in a file."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                path=dict(
                    type="string",
                    description="The path of the file, relative to root, e.g., `app/humantime/`. "
                    + "Do not give an absolute path or include '..'.",
                ),
                old_text=dict(
                    type="string",
                    description="The exact text to be replaced.",
                ),
                new_text=dict(
                    type="string",
                    description="The text to replace the old text with.",
                ),
                context_before=dict(
                    type="string",
                    description="Optional context before the old text, to target the right place.",
                ),
                context_after=dict(
                    type="string",
                    description="Optional context after the old text, to target the right place.",
                ),
                replace_all=dict(
                    type="boolean",
                    description="Replace all occurrences (default: only replace the first occurrence).",
                ),
            ),
            required=["path", "old_text", "new_text"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="integer", description="The number of occurrences that were replaced."
        )

    def __init__(
        self, root_directory: pathlib.Path, *, auto_approve: bool = False
    ) -> None:
        self.root_directory = root_directory
        self.auto_approve = auto_approve

    @override
    def call(self, params: Any) -> Any:
        path = self.root_directory / pathlib.Path(self.get_param(params, "path"))
        if not path.is_relative_to(self.root_directory):
            raise ToolError("The given path is not a relative path.")

        if not path.exists():
            raise ToolError("The given path does not exist.")

        if path.is_dir():
            raise ToolError("The given path is a directory.")

        if not githelper.is_in_repo(path):
            raise ToolError("This file is not tracked by Git and cannot be edited.")

        content = path.read_text()

        old_text = self.get_param(params, "old_text")
        new_text = self.get_param(params, "new_text")
        replace_all = params.get("replace_all", False)
        context_before = params.get("context_before")
        context_after = params.get("context_after")
        if context_before or context_after:
            before = re.escape(context_before) if context_before else ""
            after = re.escape(context_after) if context_after else ""
            pattern = f"{before}({re.escape(old_text)}){after}"
        else:
            pattern = f"({re.escape(old_text)})"

        if replace_all:
            matches = list(re.finditer(pattern, content))
        else:
            one_match = re.search(pattern, content)
            if one_match is not None:
                matches = [one_match]
            else:
                matches = []

        if not matches:
            if context_before or context_after:
                raise ToolError(
                    f"Could not find '{old_text}' with the specified context."
                )
            else:
                raise ToolError(f"Could not find '{old_text}' in the file.")

        new_content_builder: List[str] = []
        last_end = 0
        for match in matches:
            start = match.start(1)
            end = match.end(1)
            new_content_builder.append(content[last_end:start])
            new_content_builder.append(new_text)
            last_end = end
        new_content_builder.append(content[last_end:])
        new_content = "".join(new_content_builder)

        if not self.auto_approve:
            display_path = path.relative_to(self.root_directory).as_posix()
            diff = githelper.make_ansi_diff(
                content, new_content, filename_to_display=display_path
            )
            n = len(matches)
            details = f"({pluralize(n, 'replacement')})\n\n{diff}"
            details = f"({n} replacement{'s' if n > 1 else ''})\n\n{diff}"
            confirm_model_action("make the following replacement", details)

        path.write_text(new_content)
        return len(matches)


class ReadFileTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "read_file"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Read the contents of a file on a Unix-style filesystem."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                path=dict(
                    type="string",
                    description="The path to read, relative to root, e.g., `app/humantime/`. "
                    + "Do not give an absolute path or include '..'.",
                ),
                start_line=dict(
                    type="integer",
                    description="Optional 1-indexed line number to start reading from (inclusive).",
                ),
                end_line=dict(
                    type="integer",
                    description="Optional 1-indexed line number to stop reading at (inclusive).",
                ),
            ),
            required=["path"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(type="string", description="The contents of the file.")

    def __init__(self, root_directory: pathlib.Path) -> None:
        self.root_directory = root_directory

    @override
    def call(self, params: Any) -> Any:
        path = self.root_directory / pathlib.Path(self.get_param(params, "path"))
        if not path.is_relative_to(self.root_directory):
            raise ToolError("The given path is not a relative path.")

        if not path.exists():
            raise ToolError("The given path does not exist.")

        if path.is_dir():
            raise ToolError("The given path is a directory.")

        content = path.read_text()

        start_line = params.get("start_line")
        end_line = params.get("end_line")

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            start_idx = (start_line - 1) if start_line is not None else 0
            end_idx = end_line if end_line is not None else len(lines)

            if start_idx < 0 or start_idx >= len(lines):
                raise ToolError(
                    f"start_line {start_line} is out of range (file has {len(lines)} lines)."
                )

            if end_idx < start_idx:
                raise ToolError(f"end_line {end_line} is less than start_line.")

            content = "".join(lines[start_idx:end_idx])

        return content


class ListFilesTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "list_files"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "List the files under a directory on a Unix-style filesystem."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                path=dict(
                    type="string",
                    description="The directory path to list, relative to root, e.g., `app/humantime/`. "
                    + "Do not give an absolute path or include '..'.",
                ),
                recursive=dict(
                    type="boolean",
                    description="If true, list files recursively down the directory structure, respecting .gitignore. "
                    + "If false or omitted, only list the top level.",
                ),
            ),
            required=["path"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="array",
            items=dict(
                type="object",
                properties=dict(
                    path=dict(
                        type="string",
                        description="The relative path of the file.",
                    ),
                    size=dict(
                        type="integer",
                        description="The size of the file in bytes.",
                    ),
                ),
            ),
            description="A list of files under the directory, with their sizes. Directories are excluded.",
        )

    def __init__(self, root_directory: pathlib.Path) -> None:
        self.root_directory = root_directory

    @override
    def call(self, params: Any) -> Any:
        path = self.root_directory / pathlib.Path(self.get_param(params, "path"))
        if not path.is_relative_to(self.root_directory):
            raise ToolError("The given path is not a relative path.")

        if not path.exists():
            raise ToolError("The given path does not exist.")

        if not path.is_dir():
            raise ToolError("The given path is not a directory.")

        recursive = params.get("recursive", False)

        if recursive:
            # Use fd to recursively list files, respecting .gitignore
            proc = subprocess.run(
                ["fd", ".", str(path.relative_to(self.root_directory))],
                cwd=self.root_directory,
                text=True,
                capture_output=True,
                timeout=10.0,
            )

            if proc.returncode != 0:
                raise ToolError(
                    f"The `fd` command exited with an error code of {proc.returncode}."
                )

            results: List[StrDict] = []
            for line in proc.stdout.splitlines():
                if line:
                    file_path = self.root_directory / line
                    if file_path.exists():
                        size = file_path.stat().st_size if file_path.is_file() else 0
                        results.append({"path": line, "size": size})
            return results
        else:
            # Non-recursive: just list immediate children
            results = []
            for p in sorted(path.iterdir()):
                size = p.stat().st_size if p.is_file() else 0
                results.append(
                    {
                        "path": str(p.relative_to(self.root_directory)),
                        "size": size,
                    }
                )
            return results


class SearchFileContentsTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "search_repo"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return (
            "Search the files in the repository for a regex pattern using ripgrep. "
            + "Always searches from the root of the repository."
        )

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                pattern=dict(
                    type="string",
                    description="The regex pattern to search for",
                ),
                glob=dict(
                    type="string",
                    description="An optional glob pattern to constrain the files to be searched (e.g., '*.py')",
                ),
            ),
            required=["pattern"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="string",
            description="The standard output of the `rg` command.",
        )

    def __init__(self, root_directory: pathlib.Path) -> None:
        self.root_directory = root_directory

    @override
    def call(self, params: Any) -> Any:
        pattern = self.get_param(params, "pattern")
        globp = params.get("glob")

        proc = subprocess.run(
            # Unfortunately, the use of the `-g` flag means that `rg` will search files that should
            # be ignored: https://github.com/BurntSushi/ripgrep/issues/1808
            #
            # Some of these files, like the minified JavaScript files under `frontend/dist/`, have
            # very long lines. Passing `--max-columns` avoids dumping a huge number of tokens into
            # the context window, e.g., http://llm/transcript/102
            ["rg", "-C", "5", "--max-columns", "200", pattern]
            + (["-g", globp] if globp is not None else []),
            cwd=self.root_directory,
            text=True,
            capture_output=True,
            timeout=10.0,
        )

        if proc.returncode != 0:
            raise ToolError(
                f"The `rg` command exited with an error code of {proc.returncode}."
            )

        return proc.stdout


class BashCommandTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "bash_command"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Run a command using the Bash shell."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                cmd=dict(
                    type="string",
                    description="The command to run, with arguments properly quoted when needed."
                    + " The command will be run from the root of the repository.",
                ),
            ),
            required=["cmd"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="string",
            description="The standard output and standard error of the command.",
        )

    def __init__(self, root_directory: pathlib.Path, *, auto_approve: bool = False):
        self.root_directory = root_directory
        self.auto_approve = auto_approve

    @override
    def call(self, params: Any) -> Any:
        cmd = self.get_param(params, "cmd")
        if not self.auto_approve:
            confirm_model_action("run a Bash command", cmd)

        proc = subprocess.run(
            ["bash", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=self.root_directory,
        )
        return proc.stdout


class DockerBashCommandTool(BashCommandTool):
    def __init__(self, container_id: str, workdir: str):
        self.container_id = container_id
        self.workdir = workdir

    @override
    def call(self, params: Any) -> Any:
        cmd = self.get_param(params, "cmd")
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                self.workdir,
                self.container_id,
                "bash",
                "-c",
                cmd,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc.stdout


class Scratchpad:
    _contents: str

    def __init__(self) -> None:
        self._contents = ""

    def set(self, new_contents: str) -> None:
        self._contents = new_contents

    def get(self) -> str:
        return self._contents


class GetScratchpadTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "get_scratchpad"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return (
            "Retrieve thoughts from the scratchpad. Use with `set_scratchpad` to plan multi-step tasks. "
            + "There is a single global scratchpad."
        )

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(type="object", properties={})

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="string",
            description="The contents of the scratchpad.",
        )

    def __init__(self, scratchpad: Scratchpad) -> None:
        self.scratchpad = scratchpad

    @override
    def call(self, params: Any) -> Any:
        return self.scratchpad.get()


class SetScratchpadTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "set_scratchpad"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return (
            "Write down thoughts in the scratchpad. Use with `get_scratchpad` to plan multi-step tasks. "
            + "There is a single global scratchpad."
        )

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                new_contents=dict(
                    type="string", description="The new contents of the scratchpad."
                )
            ),
            required=["new_contents"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    def __init__(self, scratchpad: Scratchpad) -> None:
        self.scratchpad = scratchpad

    @override
    def call(self, params: Any) -> Any:
        self.scratchpad.set(self.get_param(params, "new_contents"))


USER_LOCATION = dict(
    type="approximate",
    city="New York",
    region="New York",
    country="US",
    timezone="America/New_York",
)


class WebSearchTool(BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "web_search"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "The built-in web-search tool."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return {}

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    @override
    def call(self, params: Any) -> Any:
        raise KgError(
            "The web search tool is a built-in tool that should not called on the client side."
        )

    @override
    def to_claude_param(self) -> anthropic_types.WebSearchTool20250305Param:
        return anthropic_types.WebSearchTool20250305Param(
            type="web_search_20250305",
            name="web_search",
            max_uses=5,
            user_location=USER_LOCATION,  # type: ignore
        )

    @override
    def to_gemini_param(self) -> StrDict:
        return dict(google_search={})

    @override
    def to_gpt_param(self) -> openai_types.ToolParam:
        return openai_types.WebSearchToolParam(
            type="web_search",
            user_location=USER_LOCATION,  # type: ignore
        )


def confirm_model_action(action: str, details: Optional[str] = "") -> None:
    prompt = (
        f"\n\nThe model would like to {colors.red(action)}:"
        + (f"\n\n{details}" if details is not None else "")
        + "\n\nDo you consent? "
    )
    response = input(prompt).strip()
    if response.lower() not in ("y", "yes"):
        raise ToolError(f"The user refused the request. Reason: {response}")
