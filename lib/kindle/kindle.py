import subprocess

from iafisher_foundation.prelude import *
from lib import simplemail

from .redacted import KINDLE_EMAIL_ADDRESS


def convert_bytes_to_epub(
    content: bytes,
    output_file: pathlib.Path,
    *,
    format: str,
    title: str,
    author: Optional[str] = None,
) -> None:
    _pandoc(
        ["-f", format],
        output_file=output_file,
        stdin=content,
        title=title,
        author=author,
    )


def convert_files_to_epub(
    input_files: List[pathlib.Path],
    output_file: pathlib.Path,
    *,
    title: str,
    author: Optional[str] = None,
) -> None:
    _pandoc(
        [f.as_posix() for f in input_files],
        output_file=output_file,
        title=title,
        author=author,
    )


def _pandoc(
    args: List[str],
    *,
    output_file: pathlib.Path,
    title: str,
    author: Optional[str] = None,
    stdin: Any = None,
) -> None:
    options = [
        "--metadata",
        f"title={title}",
        # Solves "Language tag "C" is not well-formed: Invalid subtag: C"
        # pandoc apparently defaults to LANG/LC_ALL.
        "--metadata",
        "lang=en",
    ]

    if author is not None:
        options.append("--metadata")
        options.append(f"author={author}")

    subprocess.run(
        ["pandoc"] + args + ["-o", output_file] + options,
        input=stdin,
        check=True,
    )


def send_to_device(filepath: pathlib.Path, *, title: str) -> None:
    simplemail.send_email(
        subject="kindle: send to device",
        body="",
        recipients=[KINDLE_EMAIL_ADDRESS],
        html=False,
        file_attachments=[
            simplemail.FileAttachment(
                filepath=filepath,
                maintype="application",
                subtype="epub+zip",
                # The filename is what the Kindle shows as the title of the book.
                override_filename=title + ".epub",
            )
        ],
    )
