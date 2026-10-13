"""
A manual command to review the last N commits to the monorepo with Jev.
"""

from app.jev.main import main_code_review
from iafisher.prelude import *
from iafisher.scripting import sh1
from lib import command


def main(*, n: int) -> None:
    last_n_commits = sh1(f"git log --format='%h' | head -n {n}").splitlines()
    for commit in last_n_commits:
        print(commit)
        main_code_review(commit)


if __name__ == "__main__":
    cmd = command.Command.from_function(main)
    command.dispatch(cmd)
