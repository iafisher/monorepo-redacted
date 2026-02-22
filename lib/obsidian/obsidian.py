import contextlib
import enum
from abc import ABC, abstractmethod

import yaml

from lib import githelper, oshelper
from iafisher_foundation.prelude import *

from .snapshot import snapshot

_vault_dir = pathlib.Path.home() / "Obsidian"


class Vault:
    _path: pathlib.Path

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    @classmethod
    def main(cls) -> "Vault":
        return cls.from_name("main")

    @classmethod
    def personal_site(cls) -> "Vault":
        return cls.from_name("personal-site")

    @classmethod
    def from_name(cls, name: str) -> "Vault":
        if "/" in name:
            raise KgError("vault name should not contain slashes", name=name)

        return cls(_vault_dir / name)

    def lock_file(self) -> pathlib.Path:
        return self._path / "kg.lock"

    def path(self) -> pathlib.Path:
        return self._path

    def glob(
        self, pat: str, *, subpath: Optional[PathLike] = None
    ) -> Generator[pathlib.Path, None, None]:
        globpath = self._path if subpath is None else self._path / pathlib.Path(subpath)
        for p in globpath.glob(pat):
            yield self._path / p

    def markdown_files(
        self, *, subpath: Optional[PathLike] = None
    ) -> Generator[pathlib.Path, None, None]:
        yield from self.glob("**/*.md", subpath=subpath)

    def find_note(self, title: str) -> List[pathlib.Path]:
        title = remove_suffix(title, suffix=".md")
        r: List[pathlib.Path] = []
        for p in self.markdown_files():
            if p.stem == title:
                r.append(p)

        return r

    def find_note_only_one(self, title: str) -> pathlib.Path:
        matches = self.find_note(title)
        if len(matches) == 0:
            raise KgError("note not found", title=title)
        elif len(matches) > 1:
            raise KgError("note title is ambiguous", matches=matches)

        return matches[0]

    def update_all_links(
        self, *, old_title: str, new_title: str, preserve_text: bool
    ) -> None:
        for path in self.markdown_files():
            path.write_text(
                _update_link(
                    path.read_text(),
                    old_title=old_title,
                    new_title=new_title,
                    preserve_text=preserve_text,
                )
            )


def _update_link(
    text: str, *, old_title: str, new_title: str, preserve_text: bool
) -> str:
    # TODO: case-insensitive match
    pattern1 = re.compile(
        r"\[\[(%s)(#[^\]]+)?\]\]" % re.escape(old_title), re.IGNORECASE
    )
    pattern2 = re.compile(
        r"\[\[%s(#[^\]]+)?\|([^\]]+)\]\]" % re.escape(old_title), re.IGNORECASE
    )

    if preserve_text:
        text = pattern1.sub(rf"[[{new_title}\2|\1]]", text)
    else:
        text = pattern1.sub(rf"[[{new_title}\2]]", text)
    text = pattern2.sub(rf"[[{new_title}\1|\2]]", text)
    return text


def format_month(date: datetime.date) -> str:
    return f"{date.year}-{date.month:0>2}"


dated_title_pattern = lazy_re(r"^([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?-(.+)$")


def split_dated_title(title: str) -> Tuple[datetime.date, str]:
    m = dated_title_pattern.get().match(title)
    if not m:
        raise KgError("could not parse as dated title", title=title)

    year = int(m.group(1))
    month = int(m.group(2))
    day = int(m.group(3)) if m.group(3) is not None else 1
    title = m.group(4).rstrip()
    return datetime.date(year, month, day), title


@contextlib.contextmanager
def snapshot_with_lock(
    vault: Vault,
    *,
    dry_run: bool,
    should_push: bool = False,
    extra_msg: str = "",
):
    vault_path = vault.path()
    lock_file = vault.lock_file()
    with oshelper.LockFile(lock_file, exclusive=True):
        snapshot(vault_path, dry_run=dry_run, should_push=should_push)
        try:
            yield
        except Exception:
            LOG.warning("restoring vault due to exception")
            githelper.restore_and_clean(repo=vault_path)
            raise
        else:
            snapshot(
                vault_path,
                dry_run=dry_run,
                should_push=should_push,
                extra_msg=extra_msg,
            )


@dataclass
class Block(ABC):
    document: "Document" = dataclasses.field(repr=False)
    start: int
    end: int

    @abstractmethod
    def word_count(self) -> int:
        pass

    def lines_of_code_count(self) -> int:
        return 0

    def content(self) -> str:
        return self.document.fulltext[self.start : self.end]


@dataclass
class HeaderBlock(Block):
    title: str
    level: int

    @override
    def word_count(self) -> int:
        return count_words(self.title)


@dataclass
class CodeBlock(Block):
    @override
    def word_count(self) -> int:
        return 0

    @override
    def lines_of_code_count(self) -> int:
        return self.content().count("\n") - 2


@dataclass
class TextBlock(Block):
    @override
    def word_count(self) -> int:
        return count_words(self.content())

    def is_blank(self) -> bool:
        return self.content().isspace()


@dataclass
class PropertiesBlock(Block):
    @override
    def word_count(self) -> int:
        return 0


def count_words(s: str) -> int:
    return sum(1 for w in s.split() if is_word(w))


_core = r"[A-Za-z0-9][A-Za-z0-9':?!-]*"
_word_regex = lazy_re(rf"^[\[(*\"']*{_core}.*|`{_core}`$")
del _core


def is_word(w: str) -> bool:
    return bool(_word_regex.get().match(w))


@dataclass
class Section:
    header: Optional[HeaderBlock]
    blocks: List[Block]

    def content(self) -> str:
        builder: List[str] = []
        if self.header is not None:
            builder.append(self.header.content())
        for block in self.blocks:
            builder.append(block.content())
        return "".join(builder)

    def title(self) -> str:
        return self.header.title if self.header is not None else ""

    def word_count(self) -> int:
        return sum(block.word_count() for block in self.blocks) + (
            self.header.word_count() if self.header is not None else 0
        )


@dataclass
class Document:
    fulltext: str
    blocks: List[Block]

    @classmethod
    def from_text(cls, fulltext: str) -> "Document":
        document = cls(fulltext, [])
        reader = Reader(document)
        for line in fulltext.splitlines(keepends=True):
            reader.feed(line)
        reader.done()
        return document

    @classmethod
    def from_path(cls, path: PathLike) -> "Document":
        return cls.from_text(pathlib.Path(path).read_text())

    def word_count(self) -> int:
        return sum(block.word_count() for block in self.blocks)

    def lines_of_code_count(self) -> int:
        return sum(block.lines_of_code_count() for block in self.blocks)

    def title(self) -> Optional[str]:
        for block in self.blocks:
            if isinstance(block, HeaderBlock):
                if block.level == 1:
                    return block.title
                else:
                    return None

        return None

    def properties(self) -> StrDict:
        for block in self.blocks:
            if isinstance(block, PropertiesBlock):
                content = block.content().strip()
                content = remove_prefix(content, prefix="---")
                content = remove_suffix(content, suffix="---")
                content = content.strip()
                try:
                    return yaml.safe_load(content)
                except yaml.YAMLError:
                    return {}

        return {}

    def sections(self) -> Generator[Section, None, None]:
        def is_empty(section: Section) -> bool:
            return section.header is None and len(section.blocks) == 0

        current_section = Section(None, [])
        for block in _skip_front_matter(self.blocks):
            if isinstance(block, HeaderBlock) and block.level <= 2:
                if not is_empty(current_section):
                    yield current_section

                current_section = Section(block, [])
            else:
                current_section.blocks.append(block)

        if not is_empty(current_section):
            yield current_section

    def find_section(self, title: str) -> Optional[Section]:
        for section in self.sections():
            if section.header is not None and section.header.title == title:
                return section

        return None

    def fulltext_without_properties(self) -> str:
        if self.blocks and isinstance(self.blocks[0], PropertiesBlock):
            return "".join(b.content() for b in self.blocks[1:])
        else:
            return self.fulltext

    def fulltext_without_properties_or_title(self) -> str:
        return "".join(b.content() for b in _skip_front_matter(self.blocks))


def append_to_section(
    document: Document, *, section_title: str, content: str, create_if_missing: bool
) -> str:
    builder: List[str] = []
    found = False
    for section in document.sections():
        section_text = section.content()
        if (
            not found
            and section.header is not None
            and section.header.title == section_title
        ):
            builder.append(insert_before_newlines(section_text, to_insert=content))
            found = True
        else:
            builder.append(section_text)

    if not found:
        if create_if_missing:
            builder.append(f"\n## {section_title}\n{content}")
        else:
            raise KgError("section not found", section_title=section_title)

    return "".join(builder)


def insert_before_newlines(text: str, *, to_insert: str) -> str:
    stripped = text.rstrip("\n")
    newline_count = len(text) - len(stripped)
    if newline_count > 1:
        return stripped + "\n" + to_insert.rstrip("\n") + ("\n" * newline_count)
    else:
        return text + to_insert


def _skip_front_matter(blocks: List[Block]) -> Generator[Block, None, None]:
    def is_title_header(b: Block) -> bool:
        return isinstance(b, HeaderBlock) and b.level == 1

    def is_blank(b: Block) -> bool:
        return isinstance(b, TextBlock) and b.is_blank()

    it = iter(blocks)
    while True:
        try:
            b = next(it)
        except StopIteration:
            return

        if isinstance(b, PropertiesBlock) or is_title_header(b) or is_blank(b):
            continue
        else:
            yield b
            break

    yield from it


class ReaderState(StringEnum):
    INITIAL = enum.auto()
    NORMAL = enum.auto()
    IN_CODE_BLOCK = enum.auto()
    IN_PROPERTIES = enum.auto()


class LineType(StringEnum):
    NORMAL = enum.auto()
    HEADER = enum.auto()
    CODE_BLOCK_DELIMITER = enum.auto()
    PROPERTIES_DELIMITER = enum.auto()
    EMPTY = enum.auto()


_header_basic_regex = lazy_re(r"^\s*#")
_header_full_regex = lazy_re(r"^\s*(#+)\s*(.+)$")
_properties_delimiter_regex = lazy_re(r"^---\s*$")


class Reader:
    _state: ReaderState
    _document: Document
    _block_start: int
    _line_start: int

    def __init__(self, document: Document) -> None:
        self._state = ReaderState.INITIAL
        self._document = document
        self._block_start = 0
        self._line_start = 0

    def feed(self, line: str) -> None:
        line_end = self._line_start + len(line)
        line_type = self._classify_line(line)
        S = ReaderState
        L = LineType
        match (self._state, line_type):
            # INITIAL transitions
            case (S.INITIAL, L.EMPTY):
                pass
            case (S.INITIAL, L.PROPERTIES_DELIMITER):
                self._state = S.IN_PROPERTIES
            case (S.INITIAL, L.NORMAL):
                self._state = S.NORMAL
            # INITIAL/NORMAL common transitions
            case ((S.INITIAL | S.NORMAL), L.CODE_BLOCK_DELIMITER):
                self._flush()
                self._state = ReaderState.IN_CODE_BLOCK
            case ((S.INITIAL | S.NORMAL), L.HEADER):
                self._flush()
                self._emit_header(line, line_end)
            # NORMAL transitions
            case (S.NORMAL, (L.NORMAL | L.PROPERTIES_DELIMITER | L.EMPTY)):
                pass
            # IN_CODE_BLOCK transitions
            case (S.IN_CODE_BLOCK, L.CODE_BLOCK_DELIMITER):
                self._emit_code_block(line_end)
            case (S.IN_CODE_BLOCK, _):
                pass
            # IN_PROPERTIES transitions
            case (S.IN_PROPERTIES, L.PROPERTIES_DELIMITER):
                self._emit_properties(line_end)
            case (S.IN_PROPERTIES, _):
                pass

        self._line_start = line_end

    def done(self):
        self._flush()

    def _flush(self) -> None:
        if self._block_start != self._line_start:
            if self._state == ReaderState.IN_CODE_BLOCK:
                self._document.blocks.append(
                    CodeBlock(
                        self._document, start=self._block_start, end=self._line_start
                    )
                )
            else:
                self._document.blocks.append(
                    TextBlock(
                        self._document, start=self._block_start, end=self._line_start
                    )
                )
            self._block_start = self._line_start

    def _emit_code_block(self, line_end: int) -> None:
        self._emit(CodeBlock(self._document, start=self._block_start, end=line_end))

    def _emit_header(self, line: str, line_end: int) -> None:
        m = _header_full_regex.get().match(line)
        if m is None:
            impossible()

        self._emit(
            HeaderBlock(
                self._document,
                start=self._block_start,
                end=line_end,
                level=len(m.group(1)),
                title=m.group(2),
            )
        )

    def _emit_properties(self, line_end: int) -> None:
        self._emit(
            PropertiesBlock(self._document, start=self._block_start, end=line_end)
        )

    def _emit(self, block: Block) -> None:
        self._document.blocks.append(block)
        self._block_start = block.end
        self._state = ReaderState.NORMAL

    @staticmethod
    def _classify_line(line: str) -> LineType:
        if len(line) == 0 or line.isspace():
            return LineType.EMPTY
        elif _header_basic_regex.get().match(line):
            return LineType.HEADER
        elif line.startswith("```"):
            return LineType.CODE_BLOCK_DELIMITER
        elif _properties_delimiter_regex.get().match(line):
            return LineType.PROPERTIES_DELIMITER
        else:
            return LineType.NORMAL
