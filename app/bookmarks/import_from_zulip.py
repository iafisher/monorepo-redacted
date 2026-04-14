import re

import zulip

from app.bookmarks.common import insert_bookmarks_filtering_duplicates
from app.bookmarks.models import Bookmark
from app.bookmarks.state import State
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, kgenv, kghttp, secrets
from lib.pdb import pdb

from .redacted import *


def main(*, dry_run: bool) -> None:
    authors_of_interest = fetch_authors_of_interest()

    client = get_client()
    with State.with_lock(kgenv.get_app_dir("bookmarks") / "state.json") as lock_file:
        state = lock_file.read()
        messages = fetch_messages(client, state.latest_zulip_message_id)

        time_created = timehelper.now()
        bookmarks_to_insert: List[Bookmark] = []
        for message in messages:
            author = extract_author(message)
            if author not in authors_of_interest:
                continue

            bookmarks_to_insert.append(message_to_bookmark(message, time_created))

        with pdb.connect() as db:
            insert_bookmarks_filtering_duplicates(
                db,
                bookmarks_to_insert,
                source_name_for_logging="Zulip",
                dry_run=dry_run,
            )

        if len(messages) > 0 and not dry_run:
            new_latest_message_id = messages[-1]["id"]
            LOG.info(
                "setting latest_zulip_message_id in state to %d", new_latest_message_id
            )
            state.latest_zulip_message_id = new_latest_message_id
            lock_file.write(state)


ZULIP_FOLLOWED_AUTHOR_SOURCE = "zulip_followed_author"


def message_to_bookmark(message: StrDict, time_created: datetime.datetime) -> Bookmark:
    title = message["subject"]
    url = extract_url(message)
    return Bookmark(
        bookmark_id=-1,
        source_id=message["id"],
        title=title,
        url=url,
        reading_time="",
        appeal="",
        source=ZULIP_FOLLOWED_AUTHOR_SOURCE,
        reason_archived="",
        tags=[],
        time_created=time_created,
        time_archived=None,
    )


url_pattern = re.compile(r'https://blaggregator.herokuapp.com[^"]+')


def extract_url(message: StrDict) -> str:
    content = message["content"]
    m = url_pattern.search(content)
    if m is None:
        raise KgError("could not find URL in Zulip message", content=content)

    url = m.group(0)
    response = kghttp.get(url, allow_redirects=False)
    redirect_url = response.headers.get("Location")
    if redirect_url is None:
        raise KgError(
            "blaggregator URL was not a redirect like expected",
            url=url,
            status_code=response.status_code,
            response_headers=response.headers,
        )

    return redirect_url


author_pattern1 = re.compile(r'class="user-mention".*>@([^(]+)')
author_pattern2 = re.compile(r"<strong>([^<]+)</strong> has a new blog post")


def extract_author(message: StrDict) -> str:
    content = message["content"]
    m = author_pattern1.search(content)
    if m is None:
        m = author_pattern2.search(content)

    if m is None:
        raise KgError("could not find author in Zulip message", content=content)

    return m.group(1).strip()


def get_client():
    api_key = secrets.get_or_raise("ZULIP_API_KEY")
    return zulip.Client(site=ZULIP_SITE, email=ZULIP_EMAIL, api_key=api_key)


def fetch_messages(
    client: zulip.Client, latest_message_id: Optional[int]
) -> List[StrDict]:
    if latest_message_id is not None:
        anchor = str(latest_message_id)
        num_before = 0
        num_after = 100
        include_anchor = False
    else:
        anchor = "newest"
        num_before = 100
        num_after = 0
        include_anchor = True

    request = dict(
        anchor=anchor,
        include_anchor=include_anchor,
        num_before=num_before,
        num_after=num_after,
        narrow=[
            dict(operator="channel", operand=BLOGGING_STREAM),
            dict(operator="sender", operand=BLAGGREGATOR_USER),
        ],
    )
    LOG.info("requesting messages from Zulip API: %r", request)
    response = client.get_messages(request)
    assert_success_response(response)
    messages = response["messages"]
    LOG.info("Zulip API returned %d message(s)", len(messages))
    return messages


def fetch_authors_of_interest() -> Set[str]:
    filepath = kgenv.get_app_dir("bookmarks") / "zulip-authors.txt"
    if not filepath.exists():
        return set()

    return set(
        line.strip()
        for line in filepath.read_text().splitlines()
        if not line.isspace() and not line.lstrip().startswith("#")
    )


def assert_success_response(response: StrDict) -> None:
    if response.get("result") != "success":
        raise KgError("got an error response from the Zulip API", response=response)


cmd = command.Command.from_function(
    main,
    help="Import bookmarks from the Recurse Center Zulip instance",
    less_logging=False,
)
