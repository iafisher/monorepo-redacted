from typing import Annotated

from app.bookmarks import (
    import_from_chrome,
    import_from_hn,
    import_from_rss,
    import_from_zulip,
    prune,
    webserver,
)
from app.bookmarks.common import insert_bookmarks_filtering_duplicates
from app.bookmarks.models import Bookmark
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *  # noqa: F401
from lib import command, pdb


T = Bookmark.T


def main_import_test(
    *,
    delete_existing: Annotated[
        bool, command.Extra(help="delete any existing bookmarks from the database")
    ]
) -> None:
    with pdb.connect() as db:
        if delete_existing:
            delete_all_existing_bookmarks(db)

        time_created = timehelper.now()
        models = [
            Bookmark(
                bookmark_id=-1,
                source_id="",
                title="Test bookmark 1",
                url="https://example.com/test1",
                reading_time="",
                appeal="",
                source="test",
                reason_archived="",
                tags=[],
                time_created=time_created,
                time_archived=None,
            ),
            Bookmark(
                bookmark_id=-1,
                source_id="",
                title="Test bookmark 2",
                url="https://example.com/test2",
                reading_time="",
                appeal="",
                source="test",
                reason_archived="",
                tags=[],
                time_created=time_created,
                time_archived=None,
            ),
        ]

        insert_bookmarks_filtering_duplicates(
            db, models, source_name_for_logging="fake test data", dry_run=False
        )


def delete_all_existing_bookmarks(db: pdb.Connection) -> None:
    db.execute(
        pdb.SQL("DELETE FROM {table} WHERE {time_archived} IS NULL").format(
            table=T.table,
            time_archived=T.time_archived,
        ),
    )


cmd = command.Group(help="Manage bookmarks database.")

import_cmd = command.Group(help="Import bookmarks from other sources.")
import_cmd.add("chrome", import_from_chrome.cmd)
import_cmd.add("hn", import_from_hn.cmd)
import_cmd.add("rss", import_from_rss.cmd)
import_cmd.add2("test", main_import_test, help="Import test data.", less_logging=False)
import_cmd.add("zulip", import_from_zulip.cmd)
cmd.add("import", import_cmd)

cmd.add("prune", prune.cmd)

cmd.add("serve", webserver.cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
