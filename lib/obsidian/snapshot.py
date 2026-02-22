from lib import githelper
from iafisher_foundation.prelude import *


def snapshot(
    d: pathlib.Path, *, dry_run: bool, should_push: bool, extra_msg: str = ""
) -> None:
    LOG.info("running for vault %s", d)

    if not githelper.are_there_uncommitted_changes(repo=d):
        LOG.info("no uncommitted changes, exiting")
        return

    if not dry_run:
        githelper.add_all(repo=d)

    commit_line = githelper.make_commit_line(extra_msg, repo=d)
    if dry_run:
        print(f"commit: {commit_line}")
        print()
        print("WARNING: numbers may be different because we didn't do `git add .`")
        print("Exiting without committing due to -dry-run flag.")
        return

    githelper.commit(
        commit_line, author="vaultsnapshot", email="vaultsnapshot@iafisher.com", repo=d
    )

    hsh = githelper.last_commit_hash(repo=d)
    LOG.info("made commit %s: %s", hsh, commit_line)

    if should_push:
        githelper.push(repo=d)
        LOG.info("pushed to remote")
