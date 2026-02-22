from typing import Literal

from iafisher_foundation import tabular
from iafisher_foundation.prelude import *


@dataclass
class CommandDef:
    verb: str
    has_arg: Union[bool, Literal["maybe"]]
    help: str


class CommandParseError(Exception):
    pass


def help_message(command_defs: List[CommandDef], *, as_markdown: bool = False) -> str:
    table = tabular.Table()
    for command_def in command_defs:
        match command_def.has_arg:
            case True | "maybe":
                table.row([f"  {command_def.verb} <arg>", command_def.help])
            case False:
                table.row([f"  {command_def.verb}", command_def.help])

    r = f"Available commands:\n{table.to_string(spacing=4)}"
    if as_markdown:
        return f"```\n{r}```"
    else:
        return r


def parse_command(command_defs: List[CommandDef], message: str) -> Tuple[str, str]:
    try:
        cmd, arg = message.split(maxsplit=1)
    except ValueError:
        cmd = message
        arg = ""

    for command_def in command_defs:
        if cmd == command_def.verb:
            match command_def.has_arg:
                case True:
                    if arg == "":
                        raise CommandParseError(f"{command_def.verb} takes an argument")
                case False:
                    if arg != "":
                        raise CommandParseError(
                            f"{command_def.verb} takes no arguments"
                        )
                case "maybe":
                    pass

            return command_def.verb, arg

    raise CommandParseError(f"unknown command: {cmd}")
