import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Annotated

from app.golinks.models import Golink
from iafisher_foundation import tabular, timehelper
from iafisher_foundation.prelude import *  # noqa: F401
from lib import command, pdb


# TODO(2025-11): is_deprecated column is never used. Delete?


def main_add(*, name: str, url: str) -> None:
    time_created = timehelper.now()
    with pdb.connect() as db:
        T = Golink.T
        db.execute(
            pdb.SQL(
                """
                INSERT INTO {table}(
                    {name}, {url}, {time_created}, {time_last_updated}
                )
                VALUES(%(name)s, %(url)s, %(time_created)s, %(time_created)s)
                """
            ).format(
                table=T.table,
                name=T.name,
                url=T.url,
                time_created=T.time_created,
                time_last_updated=T.time_last_updated,
            ),
            dict(name=name, url=url, time_created=time_created),
        )

    print(f"go/{name} added.")


def main_delete(name: str) -> None:
    with pdb.connect() as db:
        T = Golink.T
        row = db.fetch_one_or_zero(
            pdb.SQL(
                "DELETE FROM {table} WHERE {name} = %(name)s RETURNING {url}"
            ).format(table=T.table, name=T.name, url=T.url),
            dict(name=name),
            t=pdb.tuple_row,
        )

    if row is not None:
        print(f"Deleted go/{name} (was: {row[0]})")
    else:
        bail(f"Error: go/{name} does not exist")


def main_list(
    *,
    show_deprecated: Annotated[
        bool, command.Extra(help="show deprecated golinks that are no longer active")
    ],
) -> None:
    table = tabular.Table()
    table.header(["name", "url", "visit count", "last visited", "created"])
    with pdb.connect() as db:
        T = Golink.T
        query = pdb.SQL("SELECT {star} FROM {table} ORDER BY {name}").format(
            star=T.star, table=T.table, is_deprecated=T.is_deprecated, name=T.name
        )
        for entry in db.fetch_all(query, t=pdb.t(Golink)):
            if entry.is_deprecated:
                if show_deprecated:
                    name = f"{entry.name} (deprecated)"
                else:
                    continue
            else:
                name = entry.name

            table.row(
                [
                    name,
                    entry.url,
                    entry.visit_count,
                    entry.time_last_visited,
                    entry.time_created,
                ]
            )
    table.flush()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if not parsed_url.path.startswith("/"):
            self.send_404()
            return

        path = parsed_url.path[1:]
        host = self.headers.get("Host", "go").split(".")[0]
        if host == "archive":
            self.redirect_to(f"https://web.archive.org/web/*/{path}")
        elif host == "w":
            self.redirect_to(
                f"https://www.wikipedia.org/search-redirect.php?family=wikipedia&language=en,en&go=Go&search={path}"
            )
        elif host == "go" or host.startswith("localhost"):
            self.handle_golink(path)
        else:
            self.send_404()

    def handle_golink(self, name: str) -> None:
        with pdb.connect() as db:
            T = Golink.T
            row = db.fetch_one_or_zero(
                pdb.SQL(
                    """
                    UPDATE {table}
                    SET {visit_count} = {visit_count} + 1, {time_last_visited} = %(time)s
                    WHERE {name} = %(name)s AND NOT {is_deprecated}
                    RETURNING {url}
                    """
                ).format(
                    table=T.table,
                    visit_count=T.visit_count,
                    time_last_visited=T.time_last_visited,
                    name=T.name,
                    is_deprecated=T.is_deprecated,
                    url=T.url,
                ),
                dict(name=name, time=timehelper.now()),
                t=pdb.tuple_row,
            )

        if row is not None:
            self.redirect_to(row[0])
        else:
            url = resolve_dynamic_link(name)
            if url is not None:
                self.redirect_to(url)
            else:
                self.send_404()

    def redirect_to(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def send_404(self) -> None:
        self.send_response(404)
        self.end_headers()


def resolve_dynamic_link(path: str) -> Optional[str]:
    for pattern, replacement in DYNAMIC_REGEX_LINKS:
        if pattern.match(path):
            return pattern.sub(replacement, path)

    return None


def _go_election(match: re.Match[str]) -> str:
    year = int(match.group(1))
    if year % 4 == 0:
        return (
            f"https://en.wikipedia.org/wiki/{year}_United_States_presidential_election"
        )
    else:
        return f"https://en.wikipedia.org/wiki/{year}_United_States_elections"


def _go_ucl(match: re.Match[str]) -> str:
    year_string = match.group(1)
    if year_string is not None:
        year = int(year_string)
    else:
        today = timehelper.today()
        if today.month >= 9:
            year = today.year
        else:
            year = today.year - 1
    return f"https://en.wikipedia.org/wiki/{year}-{(year % 100) + 1:0>2}_UEFA_Champions_League"


DYNAMIC_REGEX_LINKS: List[Tuple[re.Pattern[str], Any]] = [
    # go/blocked/XYZ redirects to the Wikipedia block log for user XYZ.
    (
        re.compile("^blocked/([^/]+)$"),
        r"https://en.wikipedia.org/w/index.php?title=Special%3ALog%2Fblock&page=User%3A\1",
    ),
    # go/craigslist/XYZ searches for XYZ on Craigslist.
    (
        re.compile("^craigslist/(.+)$"),
        r"https://newyork.craigslist.org/d/for-sale/search/sss?query=\1",
    ),
    # go/define/XYZ redirects to the Dictionary.com definition of XYZ.
    (re.compile("^define/([^/]+)$"), r"https://www.dictionary.com/browse/\1"),
    # go/election/YYYY redirects to the Wikipedia page for the U.S. presidential
    # election in the year YYYY.
    (re.compile("^election/([0-9]+)$"), _go_election),
    # go/golang/XYZ redirects to the docs for the XYZ package in Go.
    (re.compile("^golang/([^/]+)$"), r"https://pkg.go.dev/\1"),
    # go/js/XYZ/ABC redirects to the MDN docs on method ABC on JavaScript object XYZ,
    # e.g. go/js/Array/join.
    (
        re.compile("^js/([^/]+)(/.+)?$"),
        r"https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/\1\2",
    ),
    # go/nasdaq/XYZ redirects to the Nasdaq listing for the ticker symbol XYZ.
    (
        re.compile(r"^nasdaq/([^/]+)"),
        r"https://www.nasdaq.com/market-activity/stocks/\1",
    ),
    # go/nyse/XYZ redirects to the NYSE listing for the ticker symbol XYZ.
    (re.compile(r"^nyse/([^/]+)"), r"https://www.nyse.com/quote/XNYS:\1"),
    # go/python/XYZ redirects to the docs for the XYZ module in Python.
    (re.compile("^python/([^/]+)$"), r"https://docs.python.org/3.11/library/\1.html"),
    # go/stroke/XYZ redirects to the animated stroke order for the Chinese character XYZ.
    (
        re.compile("^stroke/([^/]+)$"),
        r"https://www.chinesehideout.com/tools/strokeorder.php?c=\1",
    ),
    # go/syn/XYZ redirects to the Thesaurus.com entry for XYZ.
    (re.compile("^syn/([^/]+)$"), r"https://www.thesaurus.com/browse/\1"),
    # go/ucl/YYYY redirects to the Wikipedia page for the UEFA Champions League season
    # starting in the year YYYY. go/ucl redirects to the current Champions League
    # season.
    (re.compile("^ucl(?:/([0-9]+))?$"), _go_ucl),
    # go/wikicontrib/XYZ redirects to user XYZ's contributions on Wikipedia.
    (
        re.compile("^wikicontrib/([^/]+)$"),
        r"https://en.wikipedia.org/wiki/Special:Contributions/\1",
    ),
    # go/wikt/XYZ redirects to the English Wiktionary entry on XYZ.
    (re.compile(r"^wikt/([^/]+)$"), r"https://en.wiktionary.org/wiki/\1#English"),
    # go/wp/XYZ redirects to Wikipedia:XYZ.
    (re.compile("^(wp|WP)/(.+)$"), r"https://en.wikipedia.org/wiki/Wikipedia:\2"),
    (re.compile("^mos/(.+)$"), r"https://en.wikipedia.org/wiki/MOS:\1"),
    # go/wpprefix/XYZ searches for all Wikipedia articles whose title begins with XYZ.
    (
        re.compile("^wpprefix/([^/]+)$"),
        r"https://en.wikipedia.org/wiki/Special:PrefixIndex?prefix=\1&namespace=0&hideredirects=1",
    ),
    # go/youtube/XYZ searches for XYZ on YouTube.
    #
    # Note that go/youtube/history and go/youtube/later are overridden in the database
    # to point to the History and Watch Later pages, respectively.
    (
        re.compile("^youtube/(.+)$"),
        r"https://www.youtube.com/results?search_query=\1",
    ),
]


def main_serve(*, port: int) -> None:
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main_update(
    name: str, *, new_url: Annotated[str, command.Extra(name="-to")]
) -> None:
    now = timehelper.now()
    with pdb.connect() as db:
        T = Golink.T
        row = db.fetch_one_or_zero(
            pdb.SQL(
                """
                UPDATE {table}
                SET {url} = %(new_url)s, {time_last_updated} = %(now)s
                WHERE {name} = %(name)s
                RETURNING {url}
                """
            ).format(
                table=T.table,
                name=T.name,
                url=T.url,
                time_last_updated=T.time_last_updated,
            ),
            dict(name=name, new_url=new_url, now=now),
            t=pdb.tuple_row,
        )

    if row is not None:
        print(f"go/{name} is now {new_url} (was: {row[0]})")
    else:
        bail(f"Error: go/{name} does not exist")


cmd = command.Group(help="Manage go links.")
cmd.add2("add", main_add)
cmd.add2("delete", main_delete)
cmd.add2("list", main_list)
cmd.add2("serve", main_serve)
cmd.add2("update", main_update)

if __name__ == "__main__":
    command.dispatch(cmd)
