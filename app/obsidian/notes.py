import unicodedata

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
    ],
    vault: pathlib.Path = obsidian.Vault.main().path(),
    preview: Annotated[
        bool,
        command.Extra(
            help="print preview of file to be created instead of actually creating it"
        ),
    ],
) -> None:
    today = dt.date.today()
    filename = title_to_filename(opt_or(filename_override, title), today=today)

    def rel(p: pathlib.Path) -> pathlib.Path:
        return p.relative_to(vault)

    today = timehelper.today()
    archive_path = vault / "archive" / f"{today.year}" / f"{today.month:0>2}" / filename
    live_path = vault / "live" / "to-be-archived" / filename

    if archive_path.exists():
        raise KgError(
            "A file with this name already exists.", archive_path=archive_path
        )

    text = f"""\
---
date-created: "{today}"
archive-path: "{rel(archive_path)}"
created-by: "human:iafisher"
---

# {title}
"""

    if preview:
        print("Archive path:", rel(archive_path))
        print("Live path:   ", rel(live_path))
        print()
        print(text)
    else:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(text)
        live_path.hardlink_to(archive_path)
        print(rel(live_path))


def main_rename(
    *, from_: str, to: str, vault: pathlib.Path = obsidian.Vault.main().path()
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


def title_to_filename(t: str, *, today: dt.date) -> str:
    t = t.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    t = remove_suffix(t, suffix=".md")
    t = re.sub(r"[^A-Za-z0-9: -]", "", t)
    t = re.sub(r":\s*", "-", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", "-", t)

    yyyy_mm_dd = f"{today.year}-{today.month:0>2}-{today.day:0>2}"
    return f"{yyyy_mm_dd}-{t}.md"


cmd = command.Group(help="Work with Obsidian notes.")
cmd.add2("create", main_create, help="Create a new note.")
cmd.add2("rename", main_rename, help="Rename a note and update all links.")
