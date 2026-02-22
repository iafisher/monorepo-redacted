import json

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *


BOOKMARKS_PATH = (
    pathlib.Path.home()
    / "Library"
    / "Application Support"
    / "Google"
    / "Chrome"
    / "Profile 1"
    / "Bookmarks"
)


def load_bookmarks() -> Dict[str, Any]:
    with open(BOOKMARKS_PATH, "r") as f:
        return json.load(f)


def find_bookmarks_folder(
    bookmarks_dict: Dict[str, Any], folder_name: str
) -> Optional[Dict[str, Any]]:
    if "roots" in bookmarks_dict:
        for root in bookmarks_dict["roots"].values():
            if root["name"] == "synced":
                continue
            else:
                if (result := find_bookmarks_folder(root, folder_name)) is not None:
                    return result
    else:
        if bookmarks_dict["type"] == "url":
            return None

        if bookmarks_dict["name"] == folder_name:
            return bookmarks_dict

        for child in bookmarks_dict["children"]:
            if (result := find_bookmarks_folder(child, folder_name)) is not None:
                return result

    return None


def count_bookmarks(bookmarks_dict: Dict[str, Any]) -> int:
    count = 0
    for child in bookmarks_dict["children"]:
        if child["type"] == "url":
            count += 1
        elif "children" in child:
            count += count_bookmarks(child)

    return count


def parse_timestamp(t: int) -> datetime.datetime:
    # Chrome represents timestamps as 'microseconds since Jan. 1, 1601'
    # https://stackoverflow.com/questions/51343828/
    return datetime.datetime(1601, 1, 1, tzinfo=timehelper.TZ_NYC) + datetime.timedelta(
        microseconds=t
    )
