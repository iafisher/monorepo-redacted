import subprocess
from typing import TypeVar

from iafisher_foundation.prelude import *


def select(
    options: List[str],
    *,
    preview: str = "",
    preview_wrap: Optional[bool] = None,
    sorted: bool = False,
) -> str:
    if sorted:
        # `fzf` already shows in reverse order.
        options.sort(reverse=True)
    return _run(options, preview=preview, preview_wrap=preview_wrap)


T = TypeVar("T")


def select_map(
    mapped_options: List[Tuple[str, T]],
    *,
    preview: str = "",
    preview_wrap: Optional[bool] = None,
) -> T:
    name_to_value = {}
    options: List[str] = []
    for name, value in mapped_options:
        if name in name_to_value:
            raise KgError("multiple values have the same name", name=name)

        name_to_value[name] = value
        options.append(name)

    choice = _run(options, preview=preview, preview_wrap=preview_wrap)
    return name_to_value[choice]


T1 = TypeVar("T1")


def select_key(
    options: List[T1],
    *,
    key: Callable[[T1], str],
    preview: str = "",
    preview_wrap: Optional[bool] = None,
) -> T1:
    mapped_options = [(key(option), option) for option in options]
    return select_map(mapped_options, preview=preview, preview_wrap=preview_wrap)


def _run(
    options: List[str], *, preview: str = "", preview_wrap: Optional[bool] = None
) -> str:
    cmdline = ["fzf"]
    if preview:
        cmdline.append(f"--preview={preview}")
        if preview_wrap is True:
            cmdline.append("--preview-window=wrap")

    proc = subprocess.run(
        cmdline, input="\n".join(options), stdout=subprocess.PIPE, text=True
    )
    if proc.returncode != 0:
        sys.exit(proc.returncode)

    return proc.stdout.strip()
