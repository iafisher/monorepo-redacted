import os
import subprocess

from iafisher.prelude import *
from lib import command, obsidian


def main(*, vault: pathlib.Path = obsidian.Vault.main().path(), force: bool) -> None:
    os.chdir(vault)

    passed = True
    for path in sorted(pathlib.Path("live").glob("**/*.md")):
        doc = obsidian.Document.from_path(path)
        archive_path = doc.properties().get("archive-path")
        if archive_path is None:
            print(f"SKIP: {path} (no archive-path property)")
            continue

        archive_path = pathlib.Path(archive_path)
        try:
            statres = archive_path.stat()
        except FileNotFoundError:
            if force:
                print(f"{path} --> {archive_path} (archive path didn't exist, created)")
                archive_path.hardlink_to(path)
            else:
                print(f"FAIL: {path} ({archive_path} not found)")
                passed = False
        else:
            archive_ino = statres.st_ino
            my_ino = path.stat().st_ino
            if archive_ino == my_ino:
                continue

            def do_hardlink(extra: str = ""):
                print(f"{path} --> {archive_path}{extra}")
                path.unlink()
                assert archive_path is not None  # typechecker too dumb
                path.hardlink_to(archive_path)

            proc = subprocess.run(["git", "diff", "--no-index", archive_path, path])
            if proc.returncode == 0:
                do_hardlink()
            else:
                if force:
                    # TODO(2026-09): Assuming the usual case is that one of the two files is out of date,
                    # would perhaps be better to take the contents of the file with the newer timestamp.
                    do_hardlink(" (contents differ, taking archive path's contents)")
                else:
                    print(
                        f"FAIL: {archive_path} and {path} have different contents (see diff above)"
                    )
                    passed = False

    if not passed:
        sys.exit(1)


cmd = command.Command.from_function(
    main, help="Recreate hard links from live/ to archive/ if broken."
)
