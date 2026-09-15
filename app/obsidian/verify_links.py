import os

from iafisher.prelude import *
from lib import command, obsidian


def main(*, vault: pathlib.Path = obsidian.Vault.main().path()) -> None:
    passed = _verify(vault)

    if not passed:
        sys.exit(1)


def _verify(vault: pathlib.Path) -> bool:
    os.chdir(vault)

    passed = True
    for path in sorted(pathlib.Path("live").glob("**/*.md")):
        doc = obsidian.Document.from_path(path)
        archive_path = doc.properties().get("archive-path")
        if archive_path is None:
            print(f"SKIP: {path}")
        else:
            archive_path = pathlib.Path(archive_path)
            try:
                statres = archive_path.stat()
            except FileNotFoundError:
                print(f"FAIL: {path} ({archive_path} not found)")
                passed = False
            else:
                archive_ino = statres.st_ino
                my_ino = path.stat().st_ino
                if archive_ino != my_ino:
                    print(
                        f"FAIL: {path} (inode mismatch: {my_ino} != {archive_ino} {archive_path})"
                    )
                    passed = False
                else:
                    print(f"PASS: {path}")

    return passed


cmd = command.Command.from_function(
    main, help="Verify that files under live/ are hard links to archive/."
)
