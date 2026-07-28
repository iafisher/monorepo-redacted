import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import pdftotext
import trafilatura
from bs4 import BeautifulSoup, Tag

from iafisher import timehelper
from iafisher.prelude import *
from iafisher.scripting import q, sh0
from lib import command, kghttp, kgjson, kindle, localdb


Format = Literal["html", "markdown", "pdf"]


@dataclass
class Webpage:
    title: str
    author: Optional[str]
    format: Format
    content: bytes


def main_check(url: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        webpage = _download(url)
        converted_filepath = _convert_to_epub(webpage)
        sh0(f"epubcheck {q(converted_filepath.as_posix())}", check=False)
        print(f"EPUB file temporarily saved to {tmpdir}/{converted_filepath}")
        print("Press <Enter> to delete and exit")
        input()


def main_send_file(
    filepath: pathlib.Path, *, title: Optional[str] = None, author: Optional[str]
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        format = _infer_format_from_file_path(filepath)
        webpage = _clean(
            filepath.read_bytes(),
            format=format,
            override_title=title,
            override_author=author,
            fallback_title=filepath.name,
        )
        converted_filepath = _convert_to_epub(webpage)
        LOG.info("sending to Kindle")
        kindle.send_to_device(converted_filepath, title=webpage.title)
        LOG.info("sent to Kindle")


def main_send_url(
    url: str, *, title: Optional[str] = None, author: Optional[str] = None
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        webpage = _download(url, override_title=title, override_author=author)
        converted_filepath = _convert_to_epub(webpage)
        LOG.info("sending to Kindle")
        kindle.send_to_device(converted_filepath, title=webpage.title)
        LOG.info("sent to Kindle")


def _convert_to_epub(webpage: Webpage) -> pathlib.Path:
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
    return converted_filepath


@dataclass
class State(kgjson.Base):
    urls_to_clip: List[str] = dataclasses.field(default_factory=list)
    time_last_sent: Optional[dt.datetime] = None


KV_STATE_KEY = "clipper_state"


def main_weekly_edit_state() -> None:
    with tempfile.NamedTemporaryFile(prefix="clipper-state-", suffix=".json") as tmp:
        with localdb.connect() as db:
            state = _load_state(db)
            with open(tmp.name, "w") as f:
                f.write(state.serialize())

            subprocess.run([os.environ["EDITOR"], tmp.name], check=True)

            with open(tmp.name, "r") as f:
                edited_state_str = f.read().strip()

            if not edited_state_str:
                print("Aborted due to empty state.")
                return
            edited_state = state.deserialize(json.loads(edited_state_str))

            _save_state(db, edited_state)


def main_weekly_list() -> None:
    with localdb.connect() as db:
        state = _load_state(db)
        for url in state.urls_to_clip:
            print(url)


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


def main_weekly_send(
    *,
    do_not_clear: Annotated[
        bool,
        command.Extra(
            help="do not clear entries after sending (so subsequent sends will send the same URLs)"
        ),
    ],
) -> None:
    with localdb.connect() as db:
        state = _load_state(db)

        n = len(state.urls_to_clip)
        if n == 0:
            LOG.info("no URLs to send, exiting")
            return

        LOG.info("collecting batch (n=%s)", n)
        now = timehelper.now()
        _download_and_send_batch(now.date(), state.urls_to_clip)
        if not do_not_clear:
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

        print(tmpdir)
        input_files: List[pathlib.Path] = []
        for i, webpage in enumerate(webpages):
            webpage_path = pathlib.Path(f"webpage{i}{_ext_for_format(webpage.format)}")
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


def _ext_for_format(format: Format) -> str:
    match format:
        case "html":
            return ".html"
        case "markdown":
            return ".md"
        case "pdf":
            return ".pdf"


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
    format = _infer_format_from_content_type(content_type, url)
    return _clean(
        response.content,
        format=format,
        override_title=override_title,
        override_author=override_author,
        fallback_title=url,
        encoding=response.encoding,
    )


def _infer_format_from_content_type(content_type: Optional[str], url: str) -> Format:
    if content_type is None:
        LOG.warning(
            "HTTP response missing Content-Type header, assuming HTML (url=%r)", url
        )
        return "html"
    elif "text/html" in content_type:
        return "html"
    elif "application/pdf" in content_type or url.endswith(".pdf"):
        # TODO(2026-07): Pandoc can't convert PDFs so this is not actually supported.
        return "pdf"
    else:
        LOG.warning(
            "unrecognized HTTP Content-Type, falling back to HTML (url=%r, content_type=%r)",
            url,
            content_type,
        )
        return "html"


def _infer_format_from_file_path(filepath: pathlib.Path) -> Format:
    if filepath.suffix == ".html":
        return "html"
    elif filepath.suffix == ".pdf":
        return "pdf"
    else:
        LOG.warning(
            "unrecognized file extension, falling back to HTML (extension=%r)",
            filepath.suffix,
        )
        return "html"


def _clean(
    content: bytes,
    *,
    format: Format,
    override_title: Optional[str],
    override_author: Optional[str],
    encoding: Optional[str] = None,
    fallback_title: str = "Untitled",
) -> Webpage:
    title = override_title
    author = override_author

    match format:
        case "html":
            soup = BeautifulSoup(content, "html.parser")
            if title is None:
                title = _infer_html_title(soup)
            if author is None:
                author = _infer_html_author(soup)

            encoding = opt_or(encoding, "utf8")
            content = _clean_html_content(content.decode(encoding)).encode(encoding)

            if title is not None:
                content_soup = BeautifulSoup(content, "html.parser")
                _set_h1(content_soup, title)
                content = str(content_soup).encode("utf8")
        case "markdown":
            pass
        case "pdf":
            pdf = pdftotext.PDF(FakeReader(content))  # type: ignore
            format = "markdown"
            content = "\n\n".join(pdf).encode("utf8")  # type: ignore

    if title is None:
        title = fallback_title

    return Webpage(title=title, author=author, format=format, content=content)


class FakeReader:
    def __init__(self, b: bytes) -> None:
        self.b = b

    def read(self) -> bytes:
        return self.b


def _set_h1(soup: Any, title: str) -> None:
    for elem in soup.find_all("h1"):
        elem.name = "h2"

    h1 = soup.new_tag("h1")
    h1.string = title
    soup.body.insert(0, h1)


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


def _clean_html_content(text: str) -> str:
    cleaned = trafilatura.extract(text, fast=True, output_format="html")
    return opt_or(cleaned, text)


cmd = command.Group(help="Clip webpages to send to my Kindle.")

send_cmd = command.Group(help="Send individual articles to my Kindle.")
send_cmd.add2(
    "file",
    main_send_file,
    help="Send a file directly to my Kindle.",
    less_logging=False,
)
send_cmd.add2(
    "url",
    main_send_url,
    help="Send a webpage directly to my Kindle.",
    less_logging=False,
)

weekly_cmd = command.Group(help="Send a weekly bundle of articles to my Kindle.")
weekly_cmd.add2(
    "edit-state", main_weekly_edit_state, help="Manually edit the state file."
)
weekly_cmd.add2("list", main_weekly_list, help="List webpages that would be sent.")
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
cmd.add("send", send_cmd)
cmd.add("weekly", weekly_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
