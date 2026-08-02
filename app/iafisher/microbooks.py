import os

from iafisher.prelude import *
from iafisher.scripting import sh0
from lib import command


BOOK_DIRECTORY = pathlib.Path.home() / "Obsidian" / "microbooks"


def main_upload() -> None:
    for entry in os.scandir(BOOK_DIRECTORY):
        path = pathlib.Path(entry.path)
        is_book_dir = (
            entry.is_dir(follow_symlinks=False) and (path / "book.toml").exists()
        )

        if not is_book_dir:
            continue

        exe = "/Users/iafisher/.cargo/bin/mdbook"
        LOG.info("building book: %s", entry.name)
        os.chdir(path)
        sh0(f"{exe} build")
        LOG.info("uploading book: %s", entry.name)
        sh0(
            f"rsync -r --delete book/ iafisher.com:/var/www/iafisher/microbooks/{entry.name}/"
        )


cmd = command.Group(help="Helper commands for books.")
cmd.add2("upload", main_upload, help="Upload all books.", less_logging=False)
