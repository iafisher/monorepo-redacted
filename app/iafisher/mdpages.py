from typing import Annotated

import markdown
from markdown.extensions import Extension
from markdown.postprocessors import Postprocessor

from app.iafisher.common import (
    DO_NOT_PUBLISH_PROPERTY,
    HTTP_API_KEY_HEADER,
    ensure_api_key,
)
from iafisher_foundation.prelude import *
from lib import command, kghttp, obsidian


MDPAGES_TOC_THRESHOLD = 3


def main_upload(
    *,
    is_local: Annotated[
        bool, command.Extra(name="-local", help="upload to a locally-running server")
    ],
    local_url: Annotated[
        Optional[str],
        command.Extra(help="URL for local upload (only valid if -local also passed)"),
    ] = None,
    dirpath: Annotated[
        pathlib.Path, command.Extra(name="-dir", help="directory of Markdown pages")
    ] = obsidian.Vault.personal_site().path(),
    upload_all: Annotated[
        bool, command.Extra(name="-all", help="upload all pages, even if unchanged")
    ],
    verbose: bool,
    api_key: Annotated[
        Optional[str],
        command.Extra(help="use this API key instead of reading from secrets file"),
    ] = None,
) -> None:
    if api_key is None:
        api_key = ensure_api_key(local=is_local)

    if is_local:
        if local_url is None:
            base_url = "http://iafisher.test:8888"
        else:
            base_url = local_url
    else:
        base_url = "https://iafisher.com"

    images_on_site = get_images_on_site(api_key, base_url)

    if upload_all:
        hashes = {}
    else:
        hashes = get_mdpages_hashes(api_key, base_url)
    on_site_but_not_local = set(hashes.keys())

    for subpath in dirpath.glob("**/*.md"):
        if maybe_upload_page_to_site(
            api_key,
            subpath,
            base_url=base_url,
            hashes=hashes,
            root=dirpath,
            verbose=verbose,
        ):
            relpath = subpath.relative_to(dirpath)
            print(f"{relpath}: done")

        on_site_but_not_local.discard(make_mdpages_path(subpath, root=dirpath))

    delete_page_from_site(api_key, base_url, list(on_site_but_not_local))

    for image_file in dirpath.glob("uploads/*.*"):
        if image_file.name in images_on_site:
            continue

        upload_image_to_site(image_file, api_key=api_key, base_url=base_url)
        relpath = image_file.relative_to(dirpath)
        print(f"{relpath}: done")

    redirects_file = dirpath / "REDIRECTS.md"
    if redirects_file.exists():
        upload_redirects(redirects_file, api_key=api_key, base_url=base_url)


def get_mdpages_hashes(api_key: str, base_url: str) -> Dict[str, str]:
    url = f"{base_url}/mdpages/api/hashes"
    response = kghttp.get(url, headers={HTTP_API_KEY_HEADER: api_key})
    return response.json()["hashes"]


def get_images_on_site(api_key: str, base_url: str) -> List[str]:
    url = f"{base_url}/mdpages/api/list-images"
    response = kghttp.get(url, headers={HTTP_API_KEY_HEADER: api_key})
    return response.json()["files"]


def maybe_upload_page_to_site(
    api_key: str,
    path: pathlib.Path,
    *,
    base_url: str,
    hashes: Dict[str, str],
    root: pathlib.Path,
    verbose: bool,
) -> bool:
    path_str = make_mdpages_path(path, root=root)
    document = obsidian.Document.from_path(path)
    markdown_text = document.fulltext_without_properties()
    properties = document.properties()
    if (
        properties.get(DO_NOT_PUBLISH_PROPERTY, False)
        or "DO NOT UPLOAD" in markdown_text
        or "DO NOT PUBLISH" in markdown_text
    ):
        print(f"SKIPPING {path_str}")
        return False

    # IMPORTANT: Do the hash comparison on `fulltext_without_properties`, not `fulltext`
    # since the server doesn't have the full text.
    server_hash = hashes.get(path_str)
    # NOTE: The way the client calculates the hash must be kept in sync with the way the server
    # calculates the hash.
    local_hash = sha256(markdown_text)
    if server_hash is not None and server_hash == local_hash:
        return False

    if verbose:
        print(
            f"iafisher: server hash ({server_hash}) of {path_str!r} does not equal local hash ({local_hash}); uploading local version"
        )

    word_count = document.word_count()
    lines_of_code_count = document.lines_of_code_count()
    html_page = md_to_html(document)
    title = html_page.title
    html_text = html_page.content
    if not title:
        if path.stem == "INDEX":
            title = path.parent.stem
        else:
            print(f"warning: {path}: no title")
            title = path.stem

    url = f"{base_url}/mdpages/api/upload"
    response = kghttp.post(
        url,
        json=dict(
            title=title,
            path=path_str,
            markdown_text=markdown_text,
            html_text=html_text,
            toc_html=html_page.toc,
            word_count=word_count,
            lines_of_code_count=lines_of_code_count,
            properties=properties,
        ),
        headers={HTTP_API_KEY_HEADER: api_key},
    )
    if response.status_code != 200:
        print(response.text)
        print()
        print(f"uploading {path} failed")
        sys.exit(1)

    return True


def upload_image_to_site(
    image_file: pathlib.Path, *, api_key: str, base_url: str
) -> None:
    url = f"{base_url}/mdpages/api/upload-image/{image_file.name}"
    with open(image_file, "rb") as f:
        response = kghttp.post(
            url, data=f, headers={HTTP_API_KEY_HEADER: api_key}, raise_on_error=False
        )

    if response.status_code != 200:
        print(response.text)
        print()
        print(f"uploading {image_file} failed")
        sys.exit(1)


def delete_page_from_site(api_key: str, base_url: str, paths: List[str]) -> None:
    url = f"{base_url}/mdpages/api/delete"
    kghttp.post(
        url, json=dict(paths_to_delete=paths), headers={HTTP_API_KEY_HEADER: api_key}
    )
    for path in paths:
        print(f"{path}: deleted")


def upload_redirects(
    redirects_file: pathlib.Path, *, api_key: str, base_url: str
) -> None:
    redirects: List[Dict[str, str]] = []
    with open(redirects_file) as f:
        for line in f:
            if "-->" in line:
                path, target = line.split("-->")
                redirects.append(
                    dict(
                        path=path.strip().lstrip("/"),
                        target="/" + target.strip().lstrip("/"),
                    )
                )

    url = f"{base_url}/mdpages/api/upload-redirects"
    response = kghttp.post(
        url, json=dict(redirects=redirects), headers={HTTP_API_KEY_HEADER: api_key}
    )
    assert response.status_code == 200
    print("redirects: uploaded")


def make_mdpages_path(path: pathlib.Path, *, root: pathlib.Path) -> str:
    path = path.absolute()
    if path.stem == "INDEX":
        path = path.parent
    else:
        path = path.parent / path.stem

    path = path.relative_to(root)
    return str(path).rstrip("/.")


@dataclass
class HtmlPage:
    title: str
    content: str
    toc: str


def md_to_html(document: obsidian.Document) -> HtmlPage:
    md = markdown.Markdown(
        extensions=[
            "markdown.extensions.codehilite",
            "markdown.extensions.fenced_code",
            "markdown.extensions.footnotes",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            ChecklistExtension(),
        ],
        extension_configs={
            "markdown.extensions.codehilite": {
                "guess_lang": False,
            },
        },
    )

    content = md.convert(document.fulltext_without_properties())
    toc = process_toc(md.toc_tokens)  # type: ignore
    return HtmlPage(title=document.title() or "", content=content, toc=toc)


class ChecklistExtension(Extension):
    # Adapted from https://github.com/FND/markdown-checklist

    @override
    def extendMarkdown(self, md: markdown.Markdown, md_globals: Any = None):
        postprocessor = ChecklistPostprocessor(md)
        md.postprocessors.register(postprocessor, "checklist", 50)


class ChecklistPostprocessor(Postprocessor):
    # Adapted from https://github.com/FND/markdown-checklist

    list_pattern = re.compile(r"(<ul>\n<li>\[[ Xx]\])")
    item_pattern = re.compile(r"<li>\s*\[([ Xx])\]")

    @override
    def run(self, text: str) -> str:
        text = re.sub(self.list_pattern, self._convert_list, text)
        return re.sub(self.item_pattern, self._convert_item, text)

    def _convert_list(self, match: re.Match[str]) -> str:
        return match.group(1).replace("<ul>", '<ul class="checklist">')

    def _convert_item(self, match: re.Match[str]) -> str:
        state = match.group(1)
        return self.render_item(state != " ")

    def render_item(self, checked: bool) -> str:
        attr = " checked" if checked else ""
        return f'<li class="checklist-item"><input type="checkbox" {attr}>'


@dataclass
class TocHeader:
    title: str
    anchor: str


def process_toc(toc_tokens: List[StrDict]) -> str:
    # I only ever use <h1> as page title, so if present we want to make a table of
    # contents out of the <h2> headers nested beneath it.
    if len(toc_tokens) == 1 and toc_tokens[0]["level"] == 1:
        return process_toc(toc_tokens[0]["children"])

    headers_found = 0
    builder: List[str] = []
    builder.append("<ol>")
    for header_dict in toc_tokens:
        headers_found += 1
        builder.append(f'<li><a href="#{header_dict["id"]}">{header_dict["name"]}</a>')
        if header_dict["children"]:
            builder.append("<ul>")
            for subheader_dict in header_dict["children"]:
                headers_found += 1
                builder.append(
                    f'<li><a href="#{subheader_dict["id"]}">{subheader_dict["name"]}</a>'
                )
            builder.append("</ul>")
        builder.append("</li>")
    builder.append("</ol>")

    if headers_found >= MDPAGES_TOC_THRESHOLD:
        return "".join(builder)
    else:
        return ""


cmd = command.Group(help="Helper commands for Markdown pages.")
cmd.add2("upload", main_upload, help="Upload a Markdown page.")
