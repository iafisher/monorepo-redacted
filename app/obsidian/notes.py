import unicodedata

from lib import command, obsidian
from iafisher_foundation.prelude import *


def main_create(
    original_title: str, *, vault: pathlib.Path = obsidian.Vault.main().path()
) -> None:
    today = datetime.date.today()
    filename, parent = title_to_filename_and_parent(original_title, today=today)

    text = (vault / "attachments" / "templates" / "template-new-note.md").read_text()
    text = text.replace("{TITLE}", original_title)
    text = text.replace("{DATE}", today.isoformat())
    text = text.replace("{PARENT}", parent)
    (vault / filename).write_text(text)
    print(filename)


def main_rename(
    *, from_: str, to: str, vault: pathlib.Path = obsidian.Vault.main().path()
) -> None:
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


def title_to_filename_and_parent(t: str, *, today: datetime.date) -> Tuple[str, str]:
    """
    Convert title to filename and return `(filename, parent_article)`.
    """
    # Keep this in sync with `app/obsidian_plugins/notecreator/main.ts`
    t = t.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    t = remove_suffix(t, suffix=".md")
    t = re.sub(r"[^A-Za-z0-9: -]", "", t)
    t = re.sub(r":\s*", "-", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", "-", t)

    yyyy_mm = f"{today.year}-{today.month:0>2}"
    if t.startswith("book-"):
        parent = f"{today.year}-books"
    elif t.startswith("film-"):
        parent = f"{today.year}-films"
    else:
        parent = f"{yyyy_mm}"

    return f"{yyyy_mm}-{t}.md", parent


cmd = command.Group(help="Work with Obsidian notes.")
cmd.add2("create", main_create, help="Create a new note.")
cmd.add2("rename", main_rename, help="Rename a note and update all links.")
