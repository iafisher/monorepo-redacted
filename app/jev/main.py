from iafisher.prelude import *
from lib import command, jev


def main_code_review(rev: str) -> None:
    # TODO: Review diff from Git, split it into individual files, feed each file to Jev.
    todo()


GENERIC_INSTRUCTIONS = """\
You are presented with a code diff and asked to identify problems.
Only comment on the diff itself, not on any problems that already
exist in unchanged code."""


PARALLEL_STRUCTURE = f"""\
{GENERIC_INSTRUCTIONS}

Does the diff contain adjacent lines of code with parallel structure but an unexpected
similarity?

For example:

+    result1 = check(items1, strict=strict1)
+    result2 = check(items2, strict=strict1)

In the second line, `strict=strict1` is suspicious.

Does the diff contain adjacent lines of code with parallel structure but an unexpected
similarity?
"""

MISSPELLING = f"""\
{GENERIC_INSTRUCTIONS}

Does the diff contain a misspelled word?

For example

+    quesiton_key = "..."

Does the diff contain a misspelled word?
"""


def review_one_diff(diff: str) -> List[Tuple[str, float]]:
    return jev.decide_many_yes_or_no(
        diff, [("parallel_structure", PARALLEL_STRUCTURE), ("misspelling", MISSPELLING)]
    )


cmd = command.Group(help="Commands that use the Jev AI model.")
cmd.add2("code-review", main_code_review, help="Perform code review on a diff.")


if __name__ == "__main__":
    command.dispatch(cmd)
