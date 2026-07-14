import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import trafilatura
from bs4 import BeautifulSoup, Tag

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import q, sh0
from lib import command, kghttp, kgjson, kindle, localdb


@dataclass
class Webpage:
    title: str
    author: Optional[str]
    format: Literal["html", "pdf"]
    content: bytes


def main_check(url: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        _, converted_filepath = _download_and_convert(url)
        sh0(f"epubcheck {q(converted_filepath.as_posix())}", check=False)
        print(f"EPUB file temporarily saved to {tmpdir}/{converted_filepath}")
        print("Press <Enter> to delete and exit")
        input()


def main_send(
    url: str, *, title: Optional[str] = None, author: Optional[str] = None
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        webpage, converted_filepath = _download_and_convert(
            url, override_title=title, override_author=author
        )
        LOG.info("sending to Kindle")
        kindle.send_to_device(converted_filepath, title=webpage.title)
        LOG.info("sent to Kindle")


def _download_and_convert(
    url: str,
    *,
    override_title: Optional[str] = None,
    override_author: Optional[str] = None,
) -> Tuple[Webpage, pathlib.Path]:
    webpage = _download(
        url, override_title=override_title, override_author=override_author
    )
    converted_filepath = pathlib.Path("converted.epub")
    LOG.info("converting to epub")
    kindle.convert_bytes_to_epub(
        webpage.content,
        converted_filepath,
        format=webpage.format,
        title=webpage.title,
        author=webpage.author,
    )
    LOG.info("converted to epub")
    return webpage, converted_filepath


@dataclass
class State(kgjson.Base):
    urls_to_clip: List[str] = dataclasses.field(default_factory=list)
    time_last_sent: Optional[dt.datetime] = None


KV_STATE_KEY = "clipper_state"


def main_weekly_save(url: str) -> None:
    with localdb.connect() as db:
        state = _load_state(db)
        if url not in state.urls_to_clip:
            state.urls_to_clip.append(url)
            _save_state(db, state)
            LOG.info("saved state (urls_to_clip=%s)", len(state.urls_to_clip))
        else:
            LOG.warning("skipping URL already clipped (url=%r)", url)


def _load_state(db: localdb.Connection) -> State:
    state_str = localdb.kv_get(db, KV_STATE_KEY)
    if state_str is None:
        return State()
    else:
        return State.deserialize(json.loads(state_str))


def _save_state(db: localdb.Connection, state: State) -> None:
    localdb.kv_set(db, KV_STATE_KEY, state.serialize())


def main_weekly_send() -> None:
    with localdb.connect() as db:
        state = _load_state(db)

        n = len(state.urls_to_clip)
        if n == 0:
            LOG.info("no URLs to send, exiting")
            return

        LOG.info("collecting batch (n=%s)", n)
        now = timehelper.now()
        _download_and_send_batch(now.date(), state.urls_to_clip)
        state.urls_to_clip.clear()
        state.time_last_sent = now
        _save_state(db, state)
        LOG.info("saved state")


def _download_and_send_batch(date: dt.date, urls: List[str]) -> None:
    executor = ThreadPoolExecutor(max_workers=5)
    webpages = executor.map(_download, urls)
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)

        # TODO(2026-07): These input documents are all mashed together with no
        # demarcation. Claude suggests that inserting <h1> elements will cause
        # pandoc to separate them into chapters.
        #
        # http://llm/conversation/269

        input_files: List[pathlib.Path] = []
        for i, webpage in enumerate(webpages):
            webpage_path = pathlib.Path(f"webpath{i}.{webpage.format}")
            webpage_path.write_bytes(webpage.content)
            input_files.append(webpage_path)

        converted_filepath = pathlib.Path("converted.epub")

        LOG.info("converting to epub")
        title = f"Weekly batch, {date}"
        kindle.convert_files_to_epub(
            input_files, converted_filepath, title=title, author="Various"
        )
        LOG.info("converted to epub")
        LOG.info("sending to Kindle")
        kindle.send_to_device(converted_filepath, title=title)
        LOG.info("sent to Kindle")


def _download(
    url: str,
    *,
    override_title: Optional[str] = None,
    override_author: Optional[str] = None,
) -> Webpage:
    LOG.info("downloading webpage (url=%r)", url)
    response = kghttp.get(url)
    LOG.info("downloaded webpage (url=%r)", url)

    content_type = response.headers.get("Content-Type")
    if content_type is None:
        LOG.warning(
            "HTTP response missing Content-Type header, assuming HTML (url=%r)", url
        )
        format = "html"
    elif "text/html" in content_type:
        format = "html"
    elif "application/pdf" in content_type or url.endswith(".pdf"):
        # TODO(2026-07): Pandoc can't convert PDFs so this is not actually supported.
        format = "pdf"
    else:
        LOG.warning(
            "unrecognized HTTP Content-Type, falling back to HTML (url=%r, content_type=%r)",
            url,
            content_type,
        )
        format = "html"

    title = None
    author = None
    content = response.content
    if format == "html":
        soup = BeautifulSoup(response.text, "html.parser")
        title = _infer_html_title(soup)
        author = _infer_html_author(soup)
        content = _clean_html_content(response)

    if title is None:
        title = url

    # TODO(2026-07): This is structured poorly, we do the work earlier of looking up
    # title/author only to potentially throw it away here.
    if override_title is not None:
        title = override_title

    if override_author is not None:
        author = override_author

    return Webpage(title=title, author=author, format=format, content=content)


def _infer_html_title(soup: BeautifulSoup) -> Optional[str]:
    if soup.title is not None:
        return soup.title.text

    return None


def _infer_html_author(soup: BeautifulSoup) -> Optional[str]:
    meta_author = soup.find("meta", dict(name="author"))
    if isinstance(meta_author, Tag):
        meta_author_content = meta_author.get("content")
        if isinstance(meta_author_content, str):
            return meta_author_content

    return None


def _clean_html_content(response: kghttp.Response) -> bytes:
    cleaned = trafilatura.extract(response.text, fast=True, output_format="html")
    if cleaned is not None:
        return (
            cleaned.encode(response.encoding)
            if response.encoding is not None
            else cleaned.encode("utf8")
        )
    else:
        return response.content


cmd = command.Group(help="Clip webpages to send to my Kindle.")

weekly_cmd = command.Group(help="Send a bundle of articles to my Kindle weekly.")
weekly_cmd.add2(
    "save",
    main_weekly_save,
    help="Save a webpage to be sent to my Kindle.",
    less_logging=False,
)
weekly_cmd.add2(
    "send",
    main_weekly_send,
    help="Send the current weekly bundle to my Kindle.",
    less_logging=False,
)

cmd.add2("check", main_check, help="Download, convert to EPUB, and check format.")
cmd.add2(
    "send", main_send, help="Send a webpage directly to my Kindle.", less_logging=False
)
cmd.add("weekly", weekly_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
