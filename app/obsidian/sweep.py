from iafisher import timehelper
from iafisher.prelude import *
from lib import command, obsidian


def main(
    *,
    vault: pathlib.Path = obsidian.Vault.main().path(),
    older_than_days: int = 14,
    dry_run: bool = False,
    # TODO(2026-09): It would be useful to have an annotation to hide a field from the help text,
    # as for the test-only `-date` flag here and in notes.py.
    date: Optional[dt.date] = None,
) -> None:
    os.chdir(vault)

    today = opt_or_thunk(date, timehelper.today)
    older_than_date = today - datetime.timedelta(days=older_than_days)

    paths_to_unlink: List[pathlib.Path] = []
    for path in (vault / "live" / "to-be-archived").glob("*.md"):
        relpath = path.relative_to(vault)
        document = obsidian.Document.from_path(path)
        properties = document.properties()

        property_key = "date-created"
        date_created = opt_call(properties.get(property_key), parse_date)
        if date_created is None:
            LOG.warning("property %r missing from %s", property_key, relpath)
            continue

        property_key = "archive-path"
        archive_path = opt_call(properties.get(property_key), pathlib.Path)
        if archive_path is None:
            LOG.warning("property %r missing from %s", property_key, relpath)
            continue

        if not archive_path.exists():
            LOG.warning("archive path %s does not exist for %s", archive_path, relpath)
            continue

        my_stat = path.stat()
        archive_stat = archive_path.stat()
        if my_stat.st_ino != archive_stat.st_ino:
            LOG.warning(
                "%s is not a hard link to archive path %s", relpath, archive_path
            )
            continue

        if date_created < older_than_date:
            paths_to_unlink.append(path)

    for path in paths_to_unlink:
        print(path.relative_to(vault))
        if not dry_run:
            path.unlink()


cmd = command.Command.from_function(main, help="Delete old files in to-be-archived/.")
