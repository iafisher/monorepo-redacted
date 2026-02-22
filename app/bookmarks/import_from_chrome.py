from urllib.parse import urlparse
from typing import Annotated

from app.bookmarks.common import insert_bookmarks_filtering_duplicates
from app.bookmarks.models import Bookmark
from iafisher_foundation.prelude import *
from lib import chrome, command, pdb


T = Bookmark.T
CHROME_SOURCE = "chrome_unread_bookmarks"


def main(
    *,
    dry_run: bool,
    delete_existing: Annotated[
        bool,
        command.Extra(
            help="delete any existing Chrome unread bookmarks from the database"
        ),
    ]
) -> None:
    bookmarks_to_insert = fetch_unread_bookmarks_from_chrome()
    with pdb.connect() as db:
        if delete_existing:
            if dry_run:
                print("==> dry run: would have deleted existing bookmarks")
            else:
                LOG.info("deleting existing bookmarks")
                delete_existing_bookmarks_from_source(db, source=CHROME_SOURCE)

        insert_bookmarks_filtering_duplicates(
            db,
            bookmarks_to_insert,
            source_name_for_logging="Chrome unread bookmarks",
            dry_run=dry_run,
        )


def delete_existing_bookmarks_from_source(db: pdb.Connection, *, source: str) -> None:
    db.execute(
        pdb.SQL(
            "DELETE FROM {table} WHERE {source} = %(source)s AND {time_archived} IS NULL"
        ).format(
            table=T.table,
            source=T.source,
            time_archived=T.time_archived,
        ),
        dict(source=source),
    )


def fetch_unread_bookmarks_from_chrome() -> List[Bookmark]:
    all_bookmarks = chrome.load_bookmarks()
    unread_bookmarks = chrome.find_bookmarks_folder(all_bookmarks, "Unread")
    assert unread_bookmarks is not None
    return json_to_bookmark_models(unread_bookmarks)


def json_to_bookmark_models(bookmarks_dict: Dict[str, Any]) -> List[Bookmark]:
    r: List[Bookmark] = []
    for child in bookmarks_dict["children"]:
        if child["type"] == "url":
            time_created = chrome.parse_timestamp(int(child["date_added"]))
            url = child["url"]
            title = trim_title(child["name"], url)
            r.append(
                Bookmark(
                    bookmark_id=-1,
                    source_id=child["id"],
                    title=title,
                    url=url,
                    reading_time="",
                    appeal="",
                    source=CHROME_SOURCE,
                    reason_archived="",
                    tags=[],
                    time_created=time_created,
                    time_archived=None,
                )
            )
        elif "children" in child:
            r.extend(json_to_bookmark_models(child))

    return r


def trim_title(title: str, url: str) -> str:
    endings_to_strip = [
        " - The New York Times",
        " - Wikipedia",
        " | Hacker News",
        " [LWN.net]",
    ]
    for ending in endings_to_strip:
        if title.endswith(ending):
            return title[: -len(ending)]

    markers_to_strip = ["•", "·"]
    for marker in markers_to_strip:
        if marker in title:
            return title.rsplit(marker, maxsplit=1)[0].rstrip()

    try:
        domain = urlparse(url).netloc.split(".")[-2]
    except Exception:
        domain = ""

    markers_to_maybe_strip = [" - ", " | "]
    for marker in markers_to_maybe_strip:
        if marker in title:
            base, ending = title.rsplit(marker, maxsplit=1)
            ending = ending.strip().lower()
            if ending.replace(" ", "") == domain or ending.replace(" ", "-") == domain:
                return base.strip()

    return title


cmd = command.Command.from_function(
    main,
    help="Import unread bookmarks from Chrome.",
    less_logging=False,
)
