import html
import subprocess
import tempfile

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import dblog, sectionreader


def add_all(repo: Optional[PathLike] = None) -> None:
    _git(["add", "-A"], log=True, repo=repo)


def are_there_uncommitted_changes(repo: Optional[PathLike] = None) -> bool:
    return bool(_git(["status", "--porcelain"], log=False, repo=repo))


def current_branch(repo: Optional[PathLike] = None) -> str:
    return _git(["branch", "--show-current"], log=False, repo=repo).strip()


def get_root(p: PathLike) -> pathlib.Path:
    try:
        return pathlib.Path(
            _git(["rev-parse", "--show-toplevel"], log=False, repo=p).rstrip("\n")
        )
    except subprocess.CalledProcessError:
        raise KgError("not a Git repository", path=p)


def get_root_as_bytes(p: PathLike) -> bytes:
    try:
        return _git_bytes(["rev-parse", "--show-toplevel"], log=False).rstrip(b"\n")
    except subprocess.CalledProcessError:
        raise KgError("not a Git repository", path=p)


def init(repo: PathLike) -> None:
    _git(["init"], log=True, repo=repo)


def is_in_repo(p: PathLike) -> bool:
    p = pathlib.Path(p)
    if not p.is_dir():
        p = p.parent

    proc = subprocess.run(
        ["git", "-C", p, "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return proc.returncode == 0


def checkout(
    spec: str, *, quiet: bool = False, repo: Optional[PathLike] = None
) -> None:
    cmdline = ["checkout", spec]
    if quiet:
        cmdline.append("-q")
    _git(cmdline, log=False, repo=repo)


def clone(
    src: PathLike,
    *,
    to_: Optional[PathLike] = None,
    branch: str = "",
    depth: Optional[int] = None,
) -> None:
    cmdline = ["clone", str(src)]
    if to_ is not None:
        cmdline.append(str(to_))
    if branch:
        cmdline.append("--branch")
        cmdline.append(branch)
    if depth is not None:
        cmdline.append("--depth")
        cmdline.append(str(depth))
    _git(cmdline, log=True)


def make_commit_line(extra_msg: str, *, repo: PathLike) -> str:
    changes = uncommitted_changes(repo=repo)

    phrases: List[str] = []

    def append_if_nonzero(n: int, word: str) -> None:
        if n > 0:
            phrases.append(f"{n} {word}")

    append_if_nonzero(changes.added, "add")
    append_if_nonzero(changes.modified, "mod")
    append_if_nonzero(changes.deleted, "del")
    append_if_nonzero(changes.renamed, "ren")
    append_if_nonzero(changes.unknown, "unk")

    # TODO(2025-02): include size of diff
    if extra_msg:
        extra_msg = f" - {extra_msg}"
    return f"automatic snapshot{extra_msg} ({', '.join(phrases)})"


def commit(
    message: str,
    *,
    author: str,
    email: str,
    stage_all: bool = False,
    repo: Optional[PathLike] = None,
) -> None:
    # Without these, on GitHub commits will show up as 'XYZ authored and iafisher committed'
    os.environ["GIT_COMMITTER_NAME"] = author
    os.environ["GIT_COMMITTER_EMAIL"] = email

    full_author = f"{author} <{email}>"
    args = ["commit", "-m", message, "--author", full_author]
    if stage_all:
        args.append("--all")

    _git(args, log=True, repo=repo)


def last_commit_hash(repo: Optional[PathLike] = None) -> str:
    return _git(["log", "-1", "--format=%h"], log=False, repo=repo).strip()


def last_commit_time(repo: Optional[PathLike] = None) -> datetime.datetime:
    return timehelper.from_epoch_secs(
        float(_git(["log", "-1", "--format=%ct"], log=False, repo=repo).strip())
    )


def last_commit_hash_of_day(
    date: datetime.date, *, repo: Optional[PathLike] = None
) -> Optional[str]:
    dt = datetime.datetime.combine(
        date + datetime.timedelta(days=1),
        datetime.time(hour=4),
        tzinfo=timehelper.TZ_NYC,
    )
    return _git(
        ["rev-list", "-1", f"--until={dt.isoformat()}", "HEAD"], log=False, repo=repo
    ).strip()


# TODO(2025-07): Make all functions accept `Union[PathLike, bytes]`, or change this one.
def list_files(*, repo: Optional[Union[PathLike, bytes]] = None) -> List[bytes]:
    return list_files_at_commit("HEAD", repo=repo)


def list_files_at_commit(
    hsh: str, *, repo: Optional[Union[PathLike, bytes]] = None
) -> List[bytes]:
    return [
        p
        for p in _git_bytes(
            ["ls-tree", "-r", "-z", "--name-only", hsh], log=False, repo=repo
        ).split(b"\0")
        if p
    ]


def push(
    repo: Optional[PathLike] = None,
    *,
    remote: Optional[str] = None,
    branch: Optional[str] = None,
) -> None:
    cmdline = ["push"]
    if remote is not None:
        cmdline.append(remote)

    if branch is not None:
        if remote is None:
            raise KgError("if `branch` is passed, then `remote` must be passed as well")

        cmdline.append(branch)

    _git(cmdline, log=True, repo=repo)


@dataclass
class Changes:
    added: int = 0
    modified: int = 0
    deleted: int = 0
    renamed: int = 0
    unknown: int = 0


def uncommitted_changes(repo: Optional[PathLike] = None) -> Changes:
    changes = Changes()
    for line in _git(["status", "--porcelain"], log=False, repo=repo).splitlines():
        try:
            symbol, _ = line.split(maxsplit=1)
        except ValueError:
            LOG.warning("could not parse `git status` line: %r", line)
            continue

        if symbol == "A":
            changes.added += 1
        elif symbol == "M":
            changes.modified += 1
        elif symbol == "R":
            changes.renamed += 1
        elif symbol == "D":
            changes.deleted += 1
        elif symbol == "??":
            changes.unknown += 1
        else:
            LOG.warning("`git status` returned unknown symbol: %r", symbol)
            changes.unknown += 1

    return changes


def restore_and_clean(*, repo: Optional[PathLike] = None) -> None:
    _git(["restore", "."], log=True, repo=repo)
    _git(["clean", "-f", "-d"], log=True, repo=repo)


def diff(refs: List[str] = ["HEAD"], *, repo: Optional[PathLike] = None) -> str:
    return _git(["diff"] + refs, log=False, repo=repo)


def diff_to_html(diff_text: str) -> str:
    lines = diff_text.split("\n")
    html_lines: List[str] = []

    for line in lines:
        # Important to put newlines at the end of each line because the Fastmail client
        # doesn't like very long lines of HTML and will insert random newlines that break
        # the content display.
        escaped_line = html.escape(line) + "\n"

        if line.startswith("diff --git"):
            html_lines.append(f'<div class="diff-header">{escaped_line}</div>')
        elif line.startswith("index ") or line.startswith("@@"):
            html_lines.append(f'<div class="diff-info">{escaped_line}</div>')
        elif line.startswith("+++") or line.startswith("---"):
            html_lines.append(f'<div class="diff-file">{escaped_line}</div>')
        elif line.startswith("+"):
            html_lines.append(f'<div class="diff-add">{escaped_line}</div>')
        elif line.startswith("-"):
            html_lines.append(f'<div class="diff-remove">{escaped_line}</div>')
        else:
            html_lines.append(f'<div class="diff-context">{escaped_line}</div>')

    # `text-wrap-mode: wrap` is important so the diff displays reasonably on my phone.
    css = """
    <style>
    .diff-header { color: #666; font-weight: bold; }
    .diff-info { color: #888; }
    .diff-file { color: #000; font-weight: bold; }
    .diff-add { background-color: #d4edda; color: #155724; }
    .diff-remove { background-color: #f8d7da; color: #721c24; }
    .diff-context { color: #333; }
    .whole-diff div { line-height: 1.2; white-space: pre; text-wrap-mode: wrap }
    </style>
    """

    return (
        css + '<pre class="whole-diff"><code>' + "".join(html_lines) + "</code></pre>"
    )


def make_ansi_diff(
    old_text: str,
    new_text: str,
    *,
    filename_to_display: str = "text",
    word_diff: bool = False,
) -> str:
    """
    Use Git to generate a diff between `old_text` and `new_text` using ANSI color codes.
    """
    return _make_diff_common(
        old_text,
        new_text,
        git_flags=["--color=always"],
        filename_to_display=filename_to_display,
        word_diff=word_diff,
    )


def make_html_diff(old_text: str, new_text: str, *, word_diff: bool = False) -> str:
    """
    Use Git to generate a diff between `old_text` and `new_text` and style it with HTML.
    """
    return diff_to_html(
        _make_diff_common(
            old_text,
            new_text,
            git_flags=[],
            filename_to_display="text",
            word_diff=word_diff,
        )
    )


def _make_diff_common(
    old_text: str,
    new_text: str,
    *,
    git_flags: List[str],
    filename_to_display: str,
    word_diff: bool,
) -> str:
    """
    Use Git to generate a diff between `old_text` and `new_text` using ANSI color codes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = pathlib.Path(tmpdir) / f"a/{filename_to_display}"
        new_path = pathlib.Path(tmpdir) / f"b/{filename_to_display}"
        old_path.parent.mkdir(parents=True)
        new_path.parent.mkdir(parents=True)
        old_path.write_text(old_text)
        new_path.write_text(new_text)

        proc = subprocess.run(
            [
                "git",
                "diff",
            ]
            + (
                [
                    "--word-diff",
                ]
                if word_diff
                else []
            )
            + git_flags
            + [
                str(old_path),
                str(new_path),
            ],
            capture_output=True,
            text=True,
        )
        # git diff --no-index returns 1 if files differ, which is expected
        return proc.stdout


@dataclass
class BlameLine:
    commit_hash: Optional[str]
    commit_time_epoch_secs: Optional[int]
    line: str


def blame(p: PathLike, *, repo: Optional[PathLike] = None) -> List[BlameLine]:
    stdout = _git(["blame", "--porcelain", str(p)], log=False, repo=repo)
    return _blame(stdout)


def _blame(stdout: str) -> List[BlameLine]:
    blame_lines: List[BlameLine] = []
    hash_to_commit_time: Dict[str, int] = {}
    for commit_hash_str, attributes, line in _parse_git_blame(stdout):
        if all(c == "0" for c in commit_hash_str):
            commit_hash = None
            commit_time_epoch_secs = None
        else:
            commit_hash = commit_hash_str
            commit_time_epoch_secs = hash_to_commit_time.get(commit_hash)
            if commit_time_epoch_secs is None:
                commit_time_epoch_secs = int(attributes["committer-time"])
                hash_to_commit_time[commit_hash] = commit_time_epoch_secs

        blame_lines.append(
            BlameLine(
                commit_hash=commit_hash,
                commit_time_epoch_secs=commit_time_epoch_secs,
                line=line,
            )
        )
    return blame_lines


def _parse_git_blame(
    stdout: str,
) -> Generator[Tuple[str, Dict[str, str], str], None, None]:
    """
    Returns list of (commit_hash, attributes, line)
    """
    for lines in sectionreader.look_for_end_text(
        stdout, lambda line: line.startswith("\t"), exclusive=False, keep_ends=True
    ):
        if len(lines) < 2:
            raise KgError(
                "could not parse `git blame` section (expected at least 2 lines)",
                lines=lines,
            )
        commit_hash = lines[0].split(" ", maxsplit=1)[0]
        attributes = dict(line.split(" ", maxsplit=1) for line in lines[1:-1])
        # strip leading tab character
        line = lines[-1][1:]
        yield commit_hash, attributes, line


def _git(args: List[str], *, log: bool, repo: Optional[PathLike] = None) -> str:
    cmdline = _get_cmdline(repo) + args
    LOG.debug("shelling out: %r", cmdline)
    proc = subprocess.run(cmdline, check=True, text=True, stdout=subprocess.PIPE)
    if log:
        dblog.log("git_cmd_run", dict(cmdline=cmdline, cwd=os.getcwd()))
    return proc.stdout


def _git_bytes(
    args: List[str], *, log: bool, repo: Optional[Union[PathLike, bytes]] = None
) -> bytes:
    cmdline = _get_cmdline(repo) + args
    LOG.debug("shelling out: %r", cmdline)
    proc = subprocess.run(cmdline, check=True, stdout=subprocess.PIPE)
    if log:
        dblog.log("git_cmd_run", dict(cmdline=cmdline, cwd=os.getcwd()))
    return proc.stdout


def _get_cmdline(repo: Optional[Union[PathLike, bytes]]) -> List[str]:
    if repo is not None:
        return ["git", "-C", repo.decode() if isinstance(repo, bytes) else str(repo)]
    else:
        return ["git"]
