import contextlib
from typing import Annotated

from iafisher_foundation.prelude import *
from lib import command, obsidian, oshelper


def main(
    vaults: List[str],
    *,
    dry_run: Annotated[
        bool, command.Extra(help="Don't actually make the commit.")
    ] = False,
    no_push: Annotated[bool, command.Extra(help="Don't push to the remote.")] = False,
) -> None:
    for vault in vaults:
        do_one(vault, dry_run=dry_run, should_push=not no_push)


def do_one(vault_name: str, *, dry_run: bool, should_push: bool) -> None:
    vault = obsidian.Vault.from_name(vault_name)
    d = vault.path()
    try:
        os.chdir(d)
    except FileNotFoundError:
        raise KgError("Obsidian vault directory does not exist", directory=d)

    if not pathlib.Path(".git").exists():
        raise KgError("Obsidian vault is not a Git repository", directory=d)

    lock_file = vault.lock_file()
    cm: contextlib.AbstractContextManager[Union[oshelper.LockFile, None]]
    if lock_file.exists():
        LOG.info("acquiring lock file for vault")
        cm = oshelper.LockFile(lock_file, exclusive=True)
    else:
        LOG.warning("vault does not have a lock file")
        cm = contextlib.nullcontext()

    with cm:
        obsidian.snapshot(d, dry_run=dry_run, should_push=should_push)


cmd = command.Command.from_function(main, help="Snapshot an Obsidian vault with Git.")
