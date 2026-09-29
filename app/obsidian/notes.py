import unicodedata
from pathlib import Path
from typing import NewType

from iafisher import timehelper
from iafisher.prelude import *
from lib import command, obsidian


def main_create(
    *,
    title: Annotated[
        str,
        command.Extra(
            help=(
                "the title of the Markdown file "
                "(also used to infer file name, e.g., 'Some thoughts' results in '$DATE-some-thoughts.md')"
            )
        ),
    ],
    filename_override: Annotated[
        Optional[str],
        command.Extra(
            help="override -title for inferring file name (should not include date)"
        ),
    ] = None,
    vault: Path = obsidian.Vault.main().path(),
    preview: Annotated[
        bool,
        command.Extra(
            help="print preview of file to be created instead of actually creating it"
        ),
    ] = False,
    date: Annotated[Optional[dt.date], command.Extra(help="override today's date")],
) -> None:
    today = opt_or_thunk(date, timehelper.today)
    filename = format_base_filename(opt_or(filename_override, title))
    if preview:
        archive_path = format_archive_path(vault, filename, today=today)
        live_path = format_live_path(vault, archive_path)
        text = format_note_text(
            title, today=today, archive_path=archive_path.relative_to(vault)
        )
        print("Archive path:", archive_path.relative_to(vault))
        print("Live path:   ", live_path.relative_to(vault))
        print()
        print(text)
    else:
        _, live_path = create_note(vault, filename=filename, title=title, today=today)
        print(live_path.relative_to(vault))


BaseFilename = NewType("BaseFilename", str)


def create_note(
    vault: Path,
    filename: BaseFilename,
    *,
    title: str,
    today: dt.date,
    overwrite_live_path: bool = False,
    live_path_override: Optional[Path] = None,
    extra_content: str = "",
) -> Tuple[Path, Path]:
    archive_path = format_archive_path(vault, filename, today=today)
    live_path = opt_or_thunk(
        live_path_override, lambda: format_live_path(vault, archive_path)
    )

    if archive_path.exists():
        raise KgError(
            "A file with this name already exists.", archive_path=archive_path
        )

    if live_path.exists():
        if overwrite_live_path:
            live_path.unlink()
        else:
            raise KgError("The live path already exists.", live_path=live_path)

    text = format_note_text(
        title,
        today=today,
        archive_path=archive_path.relative_to(vault),
        extra_content=extra_content,
    )

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(text)
    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.hardlink_to(archive_path)
    return archive_path, live_path


def format_note_text(
    title: str,
    *,
    today: dt.date,
    archive_path: Path,
    created_by: str = "human:iafisher",
    extra_content: str = "",
) -> str:
    return (
        f"""\
---
date-created: "{today}"
archive-path: "{archive_path}"
created-by: "{created_by}"
---
# {title}
{extra_content}
""".rstrip()
        + "\n"
    )


def main_rename(
    *, from_: str, to: str, vault: Path = obsidian.Vault.main().path()
) -> None:
    # TODO(2026-09): After vault reorganization, I probably don't need this function anymore.
    destination = to
    if not destination.endswith(".md"):
        destination += ".md"

    vault_obj = obsidian.Vault(vault)
    target_path = vault_obj.find_note_only_one(from_)
    destination_matches = vault_obj.find_note(destination)
    if len(destination_matches) > 0:
        raise KgError(
            "one or more notes already exist with the destination title",
            destination=destination,
            matches=destination_matches,
        )
    destination_path = vault_obj.path() / destination

    target_path.rename(destination_path)
    vault_obj.update_all_links(
        old_title=target_path.stem, new_title=destination_path.stem, preserve_text=False
    )


def format_base_filename(t: str) -> BaseFilename:
    t = t.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    t = remove_suffix(t, suffix=".md")
    t = re.sub(r"[^A-Za-z0-9: -]", "", t)
    t = re.sub(r":\s*", "-", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", "-", t)
    return BaseFilename(t)


def format_live_path(vault: Path, archive_path: Path) -> Path:
    return vault / "live" / "to-be-archived" / archive_path.name


def format_archive_path(vault: Path, base: BaseFilename, *, today: dt.date) -> Path:
    dated_filename = f"{today.year}-{today.month:0>2}-{today.day:0>2}-{base}.md"
    return vault / "archive" / f"{today.year}" / f"{today.month:0>2}" / dated_filename


cmd = command.Group(help="Work with Obsidian notes.")
cmd.add2("create", main_create, help="Create a new note.")
cmd.add2("rename", main_rename, help="Rename a note and update all links.")
