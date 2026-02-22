from typing import Annotated

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, dblog, kgenv


def main(
    *,
    max_age_days: Annotated[
        int, command.Extra(help="delete log files older than this")
    ],
    directory: pathlib.Path = kgenv.get_ian_dir() / "logs",
    dry_run: bool = False,
) -> None:

    cutoff = timehelper.now() - datetime.timedelta(days=max_age_days)
    LOG.info(
        "rotating logs in %s with max_age_days=%d (cutoff: %s)",
        directory,
        max_age_days,
        cutoff,
    )
    deleted_count = 0
    for p in directory.glob("**/*.log"):
        try:
            time_created = datetime.datetime.fromisoformat(p.stem)
        except ValueError:
            LOG.warning("unable to parse file name as datetime: %s", p)
            continue

        # 2025-11: This happened for instance when I manually created a 2025-11-11.log file and
        # logrotate crashed on every run when it tried to compare the resulting naive datetime
        # with the aware datetime `cutoff` below.
        if not timehelper.is_datetime_aware(time_created):
            LOG.warning("datetime was parsed as naive: %s", p)
            continue

        if time_created < cutoff:
            LOG.info("deleting %s (created at %s, too old)", p, time_created)
            if not dry_run:
                os.remove(p)
                dblog.log("log_file_deleted", dict(path=str(p)))
            deleted_count += 1
        else:
            LOG.info("not deleting %s (created at %s, not too old)", p, time_created)

    LOG.info("deleted %d log file(s)", deleted_count)


cmd = command.Command.from_function(main, help="Rotate logs.", less_logging=False)

if __name__ == "__main__":
    command.dispatch(cmd)
