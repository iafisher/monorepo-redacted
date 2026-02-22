from typing import Iterable, TypeVar

from iafisher_foundation.prelude import *


def look_for_end_text(
    text: str, pred: Callable[[str], bool], *, exclusive: bool, keep_ends: bool
) -> Generator[List[str], None, None]:
    yield from look_for_end(
        text.splitlines(keepends=keep_ends), pred, exclusive=exclusive
    )


T1 = TypeVar("T1")


def look_for_end(
    xs: Iterable[T1], pred: Callable[[T1], bool], *, exclusive: bool
) -> Generator[List[T1], None, None]:
    section: List[T1] = []
    for x in xs:
        if pred(x):
            if not exclusive:
                section.append(x)
            yield section
            section = []
        else:
            section.append(x)

    if section:
        yield section


def look_for_start_text(
    text: str,
    pred: Callable[[str], bool],
    *,
    exclusive: bool,
    keep_init: bool,
    keep_ends: bool
) -> Generator[List[str], None, None]:
    yield from look_for_start(
        text.splitlines(keepends=keep_ends),
        pred,
        exclusive=exclusive,
        keep_init=keep_init,
    )


T2 = TypeVar("T2")


def look_for_start(
    xs: Iterable[T2], pred: Callable[[T2], bool], *, exclusive: bool, keep_init: bool
) -> Generator[List[T2], None, None]:
    section: List[T2] = []
    seen_first = False
    for x in xs:
        if pred(x):
            if not seen_first:
                seen_first = True
                if section:
                    yield section
            else:
                yield section

            section = []
            if not exclusive:
                section.append(x)
        else:
            if seen_first or keep_init:
                section.append(x)

    if section:
        yield section


"""
TODO(2025-04): Seems like this library could be simplified with a more abstract `group` function
that takes in a `merge` argument.

`merge` would take in the current line and maybe the current group, and return START, END, MERGE,
DROP etc.
"""
