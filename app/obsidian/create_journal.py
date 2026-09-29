from app.obsidian.notes import create_note, format_archive_path, format_base_filename
from iafisher import timehelper
from iafisher.prelude import *
from lib import command, obsidian


def main(*, vault: pathlib.Path = obsidian.Vault.main().path()) -> None:
    path = create_journal(vault, today=timehelper.today())
    if path is None:
        print("Journal file already exists.")
    else:
        print(f"Journal file created: {path.relative_to(vault)}")


def create_journal(vault: pathlib.Path, *, today: dt.date) -> Optional[pathlib.Path]:
    today = today.replace(day=1)

    base_filename = format_base_filename("journal")
    archive_path = format_archive_path(vault, base_filename, today=today)
    if archive_path.exists():
        return None

    last_month = timehelper.last_month(today)
    next_month = timehelper.next_month(today)
    link_format = "[[%Y-%m-%d-journal|%B]]"
    extra_content = f"❮ {last_month.strftime(link_format)} | {today.strftime('%B')} | {next_month.strftime(link_format)} ❯"
    archive_path, _ = create_note(
        vault,
        base_filename,
        title=today.strftime("%B %Y"),
        today=today,
        overwrite_live_path=True,
        live_path_override=(vault / "live" / "journal.md"),
        extra_content=extra_content,
    )
    return archive_path


cmd = command.Command.from_function(main, help="Create the monthly journal note.")
