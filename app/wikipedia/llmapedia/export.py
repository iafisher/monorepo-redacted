import csv
import json
import time
import urllib.parse

from app.wikipedia.common import USER_AGENT
from iafisher_foundation.prelude import *
from lib import iterhelper, kghttp


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
VITAL_ARTICLES_CATEGORY = "Level-3 vital articles by quality"
BATCH_SIZE = 50
SLEEP_BETWEEN_REQUESTS = 5.0


# `vital_list` can be downloaded from https://github.com/GeogSage/Wiki_Vital/blob/main/Vitallist_AllLevels_15June2025_Full.csv
# Some titles that failed to be downloaded (either because of non-ASCII characters, renaming, or unknown reasons).
# titles = [
#     "African traditional religions",
#     "Acid–base reaction",
#     "Kurt Gödel",
#     "Newton's laws of motion",
#     "Simón Bolívar",
#     "Niccolò Machiavelli",
#     "Swahili",
#     "René Descartes",
#     # "HIV/AIDS",
#     "São Paulo",
#     "Michael Jackson",
#     "South Africa",
#     "Argentina",
#     "Turkey",
# ]
def main(*, dest: pathlib.Path, vital_list: pathlib.Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    titles = fetch_vital_article_titles(vital_list)
    LOG.info("fetched %d vital article title(s)", len(titles))

    total = 0
    for i, is_last in iterhelper.iter_is_last(list(range(0, len(titles), BATCH_SIZE))):
        batch = titles[i : i + BATCH_SIZE]
        LOG.info(
            "fetching wikitext for articles %d-%d of %d",
            i + 1,
            min(i + BATCH_SIZE, len(titles)),
            len(titles),
        )
        pages = fetch_wikitext_batch(batch)
        for title, wikitext in pages.items():
            safe_title = _title_to_filename(title)
            (dest / safe_title).write_text(
                json.dumps({"title": title, "wikitext": wikitext})
            )
            total += 1

        if not is_last:
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    LOG.info("wrote %d article(s) to %s", total, dest)


def fetch_vital_article_titles(vital_list: pathlib.Path) -> List[str]:
    r: List[str] = []
    with open(vital_list, "r", newline="", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Vital_Level"] in ("1", "2", "3"):
                r.append(row["Article"])
    return r


def fetch_vital_article_titles_by_api() -> List[str]:
    # This function is deprecated since the vital articles categories are not actually
    # comprehensive.
    subcategories = _fetch_category_members(VITAL_ARTICLES_CATEGORY, cmtype="subcat")
    LOG.info(
        "found %d subcategory/ies under %r", len(subcategories), VITAL_ARTICLES_CATEGORY
    )

    titles: List[str] = []
    for subcat in subcategories:
        subcat_name = subcat.removeprefix("Category:")
        members = _fetch_category_members(subcat_name, cmtype="page")
        LOG.info("found %d article(s) in %r", len(members), subcat_name)
        titles.extend(members)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return titles


def fetch_wikitext_batch(titles: List[str]) -> Dict[str, str]:
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": "|".join(titles),
        "rvslots": "main",
        "rvprop": "content",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    }
    response = kghttp.get(
        WIKIPEDIA_API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
    )
    data = response.json()
    if "query" not in data:
        raise KgError("unexpected response from Wikipedia API", data=data)

    result: Dict[str, str] = {}
    for page in data["query"]["pages"]:
        if "missing" in page:
            LOG.warning("page not found: %r", page.get("title"))
            continue
        title = page["title"]
        revisions = page.get("revisions")
        if not revisions:
            LOG.warning("no revisions for page: %r", title)
            continue
        result[title] = revisions[0]["slots"]["main"]["content"]
    return result


def _fetch_category_members(category: str, *, cmtype: str) -> List[str]:
    members: List[str] = []
    params: Dict[str, str] = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": cmtype,
        "cmlimit": "max",
        "format": "json",
        "formatversion": "2",
    }
    while True:
        response = kghttp.get(
            WIKIPEDIA_API + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        )
        data = response.json()
        if "query" not in data:
            raise KgError(
                "unexpected response from Wikipedia API",
                category=category,
                data=data,
            )
        for member in data["query"]["categorymembers"]:
            members.append(remove_prefix(member["title"], prefix="Talk:"))
        if "continue" not in data:
            break
        params.update(data["continue"])
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    return members


def _title_to_filename(title: str) -> str:
    safe = title.replace("/", "_")
    return urllib.parse.quote(safe, safe=" _-.()")
