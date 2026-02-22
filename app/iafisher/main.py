import shlex
import shutil
import subprocess
import sys
from typing import Annotated

import yaml

from app.iafisher import mdpages, stats
from app.iafisher.common import CODE_PATH, ensure_api_key
from app.iafisher.provision_deploy import (
    main_deploy,
    main_list_deploys,
    main_provision,
    main_rollback,
)
from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import sh0
from lib import command, kghttp, obsidian


def main_django(
    django_args: Annotated[List[str], command.Extra(passthrough=True)]
) -> None:
    run_django(list(django_args))


def run_django(args: List[str]) -> None:
    d = "/var/iafisher"
    code = f"{d}/deployments/current/code"
    args_str = shlex.join(args)
    cmd = f"source {d}/env-for-sourcing && {code}/.venv/bin/python3 {code}/manage.py {args_str}"
    print(cmd)
    proc = subprocess.run(["ssh", "iafisher.com", "-t", cmd])
    sys.exit(proc.returncode)


def main_psql() -> None:
    sh0("ssh iafisher.com -t psql")


def main_local_runserver(*, p: int = 8888):
    subprocess.run(
        [
            CODE_PATH / ".venv" / "bin" / "python3",
            CODE_PATH / "manage.py",
            "runserver",
            str(p),
        ]
    )


def main_blog_mail(
    *,
    url: Annotated[str, command.Extra(help="URL of blog post")],
    test_recipient: Annotated[
        Optional[str],
        command.Extra(
            help="send to a single test recipient instead of the mailing list"
        ),
    ] = None,
    allow_resend: Annotated[
        bool,
        command.Extra(
            help="allow the re-sending of a campaign that has already been sent"
        ),
    ],
) -> None:
    django_args: List[str] = ["send_newsletter", url]
    if test_recipient:
        django_args.append("--test-recipient")
        django_args.append(test_recipient)

    if allow_resend:
        django_args.append("--allow-resend")

    run_django(django_args)


def main_blog_upload(
    *,
    is_local: Annotated[
        bool, command.Extra(name="-local", help="upload to a locally-running server")
    ],
    post_path: Annotated[
        Optional[pathlib.Path],
        command.Extra(
            name="-path",
            help="path to blog post; if not supplied, will search for ready-to-publish posts",
        ),
    ] = None,
    local_url: Annotated[
        Optional[str],
        command.Extra(help="URL for local upload (only valid if -local also passed)"),
    ] = None,
    no_confirm: Annotated[bool, command.Extra(help="don't require confirmation")],
    api_key: Annotated[
        Optional[str],
        command.Extra(help="use this API key instead of reading from secrets file"),
    ] = None,
) -> None:
    if not is_local:
        raise NotImplementedError(
            "this command has not been updated to work with the new blog vault"
        )

    if api_key is None:
        api_key = ensure_api_key(local=is_local)

    if post_path is None:
        post_path = find_post_to_publish()

    print("Found post to publish:", post_path)
    post_details = validate_post(post_path)

    if not no_confirm:
        confirm_details(post_details, local=is_local)

    if is_local and local_url is None:
        local_url = "http://iafisher.test:8888"

    post_url = upload_post_to_site(api_key, post_details, local_url=local_url)
    if not is_local:
        update_post_file(post_path, post_url, post_details.sha256_hash)


@dataclass
class PostDetails:
    title: str
    slug: str
    summary: str
    markdown_text: str
    sha256_hash: str
    is_featured: bool
    document: obsidian.Document

    def to_api_payload(self) -> StrDict:
        return dict(
            title=self.title,
            slug=self.slug,
            summary=self.summary,
            markdown_text=self.markdown_text,
            is_featured=self.is_featured,
        )


def find_post_to_publish() -> pathlib.Path:
    vault = obsidian.Vault.main()
    candidates: List[pathlib.Path] = []
    for path in vault.markdown_files(subpath="blog/drafts"):
        document = obsidian.Document.from_path(path)
        properties = document.properties()
        if properties.get("iafisher-status") == "to-publish":
            candidates.append(path)

    assert len(candidates) == 1, "candidates: " + repr(candidates)
    return candidates[0]


def validate_post(post_path: pathlib.Path) -> PostDetails:
    document = obsidian.Document.from_path(post_path)
    properties = document.properties()
    post_text = document.fulltext_without_properties()

    ensure_no_wikilinks(post_text)
    ensure_no_todos(post_text)
    ensure_ready_to_publish(post_path, properties)

    sha256_hash = sha256b(post_path.read_bytes())

    return PostDetails(
        title=properties["iafisher-title"],
        slug=properties["iafisher-slug"],
        summary=properties["iafisher-summary"],
        markdown_text=post_text,
        sha256_hash=sha256_hash,
        is_featured=properties["iafisher-is-featured"],
        document=document,
    )


Properties = Dict[str, Any]


def serialize_obsidian_properties(properties: Properties) -> str:
    block = yaml.dump(properties)
    if not block.endswith("\n"):
        block += "\n"
    return f"---\n{block}---"


WIKILINKS_PATTERN = lazy_re(r"\[\[.*\]\]")


def ensure_no_wikilinks(post_text: str) -> None:
    assert WIKILINKS_PATTERN.get().search(post_text) is None


def ensure_no_todos(post_text: str) -> None:
    assert "TODO" not in post_text
    assert "EDIT" not in post_text
    assert "CHECK" not in post_text


def ensure_ready_to_publish(post_path: pathlib.Path, properties: Properties) -> None:
    assert post_path.parent.name == "drafts"
    assert properties["iafisher-status"] == "to-publish"
    assert not any(value == "TODO" for value in properties.values())


def confirm_details(post_details: PostDetails, *, local: bool) -> None:
    word_count = post_details.document.word_count()
    print("Title:      ", post_details.title)
    print("Text:       ", f"~{word_count} words")
    print("Slug:       ", post_details.slug)
    print("Is featured:", post_details.is_featured)
    print()

    destination = "to PUBLIC site" if not local else "to local webserver"
    r = input(f"Publish {destination}? ").strip().lower()
    if not (r == "y" or r == "yes"):
        print("Aborted.", file=sys.stderr)
        sys.exit(1)


def upload_post_to_site(
    api_key: str, post_details: PostDetails, *, local_url: Optional[str] = None
) -> str:
    base_url = local_url or "https://iafisher.com"
    url = base_url + "/blog/api/upload"
    response = kghttp.post(
        url,
        json=post_details.to_api_payload(),
        headers={"X-Iafisher-Api-Key": api_key},
    )
    urlpath = response.json()["path"]
    return base_url + urlpath


def update_post_file(post_path: pathlib.Path, post_url: str, sha256_hash: str) -> None:
    document = obsidian.Document.from_path(post_path)
    properties = document.properties()
    properties["iafisher-status"] = "published"
    properties["iafisher-url"] = post_url
    properties["iafisher-sha256_hash"] = sha256_hash

    properties_text = serialize_obsidian_properties(properties)
    post_path.write_text(properties_text + document.fulltext_without_properties())

    # move out of drafts folder
    today = datetime.date.today()
    destination_dir = post_path.parent.parent / str(today.year)
    destination_path = destination_dir / post_path.name.replace("Draft - ", "Blog - ")

    if not destination_dir.exists():
        destination_dir.mkdir()
    else:
        # TODO: front-load this check
        assert not destination_path.exists()

    shutil.move(post_path, destination_path)


cmd = command.Group(help="Management commands for iafisher.com")

cmd.add2("deploy", main_deploy, help="Deploy a new version of the server.")
cmd.add2(
    "django", main_django, help="Run Django's manage.py script on the prod server."
)
cmd.add2("provision", main_provision, help="Provision a new server from scratch.")
cmd.add2("psql", main_psql, help="Launch a psql shell connected to the prod database.")

blog_cmd = command.Group(help="Helper commands for my personal blog.")
blog_cmd.add2("mail", main_blog_mail, help="Send the newsletter for a new blog post.")
blog_cmd.add2("upload", main_blog_upload, help="Upload a new blog post.")
cmd.add("blog", blog_cmd)

cmd.add("mdpages", mdpages.cmd)

cmd.add2("list-deploys", main_list_deploys)

local_cmd = command.Group(help="Helper commands for local development.")
local_cmd.add2("runserver", main_local_runserver, help="Run the development server.")
cmd.add("local", local_cmd)

cmd.add2("rollback", main_rollback, help="Roll back to a previous deployment.")

cmd.add("stats", stats.cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
