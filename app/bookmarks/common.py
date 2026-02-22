from app.bookmarks.models import Bookmark
from lib import pdb
from iafisher_foundation.prelude import *

T = Bookmark.T


def insert_bookmarks_filtering_duplicates(
    db: pdb.Connection,
    bookmarks: List[Bookmark],
    *,
    source_name_for_logging: str,
    dry_run: bool,
) -> None:
    if dry_run:
        print(
            f"==> dry run: would have imported {len(bookmarks)} (count may be overestimate due to duplicates filtered in SQL)"
        )
        return

    if len(bookmarks) > 0:
        LOG.info(
            "importing %d item(s) (including possible duplicates) from %s",
            len(bookmarks),
            source_name_for_logging,
        )
        rows = db.execute_many_and_fetch_all(
            pdb.SQL(
                "INSERT INTO {}({}) VALUES({}) ON CONFLICT ({url}) DO NOTHING RETURNING url"
            ).format(T.table, T.star_for_insert, T.placeholders, url=T.url),
            [dataclasses.asdict(bookmark) for bookmark in bookmarks],
        )
        inserted_urls = [row[0] for row in rows]
        LOG.info(
            "imported %d bookmark(s) from %s: %r",
            len(inserted_urls),
            source_name_for_logging,
            inserted_urls,
        )
    else:
        LOG.info("no bookmarks to insert from %s", source_name_for_logging)
