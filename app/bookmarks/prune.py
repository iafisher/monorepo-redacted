from app.bookmarks.models import Bookmark
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, pdb


T = Bookmark.T


NEVER_PRUNE_BEFORE = datetime.datetime(2025, 8, 30, tzinfo=timehelper.TZ_NYC)


def main(*, days_to_retain: int, dry_run: bool) -> None:
    cutoff = timehelper.now() + datetime.timedelta(days=-days_to_retain)

    with pdb.connect() as db:
        rows = db.fetch_all(
            pdb.SQL(
                """
                SELECT {bookmark_id}, {url}
                FROM {table}
                WHERE
                  {time_archived} IS NULL
                  AND {time_created} < %(cutoff)s
                  AND {time_created} >= %(never_prune_before)s
                """
            ).format(
                table=T.table,
                bookmark_id=T.bookmark_id,
                url=T.url,
                time_archived=T.time_archived,
                time_created=T.time_created,
            ),
            dict(cutoff=cutoff, never_prune_before=NEVER_PRUNE_BEFORE),
            t=pdb.tuple_row,
        )
        LOG.info("found %d bookmark(s) eligible for archiving: %r", len(rows), rows)
        bookmark_ids = [row[0] for row in rows]

        if len(bookmark_ids) == 0:
            return

        if dry_run:
            print(f"==> dry run: would have archived {len(rows)}")
        else:
            time_archived = timehelper.now()
            db.execute(
                pdb.SQL(
                    """
                    UPDATE {table}
                    SET {time_archived} = %(time_archived)s, {reason_archived} = 'expired'
                    WHERE {bookmark_id} = ANY(%(bookmark_ids)s)
                    """
                ).format(
                    table=T.table,
                    time_archived=T.time_archived,
                    reason_archived=T.reason_archived,
                    bookmark_id=T.bookmark_id,
                ),
                dict(time_archived=time_archived, bookmark_ids=bookmark_ids),
            )
            LOG.info("archived %d bookmark(s)", len(bookmark_ids))


cmd = command.Command.from_function(
    main,
    help="Prune bookmarks that have not been read after a certain time",
    less_logging=False,
)
