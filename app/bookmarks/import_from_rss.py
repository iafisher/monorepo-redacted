import html
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from app.bookmarks.common import insert_bookmarks_filtering_duplicates
from app.bookmarks.models import Bookmark
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, kgenv, kghttp, pdb


T = Bookmark.T


def main(*, dry_run: bool) -> None:
    filepath = kgenv.get_ian_dir() / "apps" / "bookmarks" / "rss_feeds.txt"
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        import_from_feed(line, dry_run=dry_run)


RSS_FEED_IMPORTER_SOURCE = "rss_feed_importer"


@dataclass
class FeedItem:
    title: str
    url: str

    def to_bookmark(self, time_created: datetime.datetime) -> Bookmark:
        return Bookmark(
            bookmark_id=-1,
            source_id="",
            title=self.title,
            url=self.url,
            reading_time="",
            appeal="",
            source=RSS_FEED_IMPORTER_SOURCE,
            reason_archived="",
            tags=[],
            time_created=time_created,
            time_archived=None,
        )


# Don't import items from before this date.
cutoff = datetime.datetime(year=2025, month=8, day=23, tzinfo=timehelper.TZ_NYC)


def import_from_feed(url: str, *, dry_run: bool) -> None:
    feed_items = fetch_from_feed(url)
    time_created = timehelper.now()
    with pdb.connect() as db:
        bookmarks = [
            feed_item.to_bookmark(time_created=time_created) for feed_item in feed_items
        ]
        insert_bookmarks_filtering_duplicates(
            db,
            bookmarks,
            source_name_for_logging=f"RSS feed at {url}",
            dry_run=dry_run,
        )


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _get_text(elem: ET.Element, names: List[str]) -> Optional[str]:
    for name in names:
        node = elem.find(name)
        if node is not None and node.text:
            t = node.text.strip()
            if t:
                return t
    return None


def _parse_iso8601(dt: str) -> Optional[datetime.datetime]:
    try:
        # Handle trailing Z
        if dt.endswith("Z"):
            dt = dt[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(dt)
    except Exception:
        return None


def _parse_date(text: Optional[str]) -> Optional[datetime.datetime]:
    if not text:
        return None
    # Try RFC 822/1123 (common in RSS)
    try:
        d = parsedate_to_datetime(text)
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d
    except Exception:
        pass
    # Try ISO-8601 (common in Atom)
    d = _parse_iso8601(text)
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def _get_atom_link(entry: ET.Element) -> Optional[str]:
    # Prefer rel="alternate", then any href
    for link in entry.findall(".//{*}link"):
        rel = link.get("rel")
        href = link.get("href")
        if href and (rel in (None, "", "alternate")):
            return href
    # Fallback: some feeds put link text inside <link>
    txt = entry.findtext(".//{*}link")
    return txt.strip() if txt and txt.strip() else None


def fetch_from_feed(feed_url: str) -> List[FeedItem]:
    LOG.info("fetching items from RSS feed at %s", feed_url)
    # Some feeds (e.g., LessWrong) return HTTP 403 unless `User-Agent` is set.
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    }
    response = kghttp.get(feed_url, headers=headers)
    LOG.info("got %d byte(s) from %s", len(response.content), feed_url)

    root = ET.fromstring(response.content)

    items: List[FeedItem] = []
    root_tag = _strip_ns(root.tag)

    skipped_missing_info = 0
    skipped_date_cutoff = 0

    if root_tag.lower() == "rss" or root_tag.lower() == "rdf":
        # RSS 2.0 (items under channel) or RDF-style
        candidates = root.findall(".//{*}item") or root.findall(".//item")
        for it in candidates:
            title = _get_text(it, [".//{*}title", "title"])
            url = _get_text(it, [".//{*}link", "link"])
            if not title or not url:
                skipped_missing_info += 1
                continue

            # pubDate or dc:date
            dt = _get_text(it, [".//{*}pubDate", "pubDate", ".//{*}date", "date"])
            when = _parse_date(dt)
            if when is not None and when < cutoff:
                skipped_date_cutoff += 1
                continue
            items.append(FeedItem(title=html.unescape(title), url=url.strip()))
    elif root_tag.lower() == "feed":
        # Atom
        entries = root.findall(".//{*}entry") or root.findall(".//entry")
        for entry in entries:
            title = _get_text(entry, [".//{*}title", "title"])
            url = _get_atom_link(entry)
            if not title or not url:
                skipped_missing_info += 1
                continue

            # published or updated
            dt = _get_text(
                entry, [".//{*}published", "published", ".//{*}updated", "updated"]
            )
            when = _parse_date(dt)
            if when is not None and when < cutoff:
                skipped_date_cutoff += 1
                continue
            items.append(FeedItem(title=html.unescape(title), url=url.strip()))
    else:
        LOG.warning("unknown feed root <%s> at %s", root_tag, feed_url)

    LOG.info(
        "skipped due to missing data: %d (url: %s)", skipped_missing_info, feed_url
    )
    LOG.info("skipped due to date cutoff: %d (url: %s)", skipped_date_cutoff, feed_url)

    # Deduplicate by URL while preserving order
    seen: Set[str] = set()
    deduped: List[FeedItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)

    return deduped


cmd = command.Command.from_function(
    main, help="Import bookmarks from RSS feeds", less_logging=False
)
