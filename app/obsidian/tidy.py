import contextlib
from collections import defaultdict

from iafisher_foundation import colors, timehelper
from iafisher_foundation.prelude import *
from lib import command, githelper, obsidian


def main(*, write: bool = False) -> None:
    dry_run = not write

    maybe_lock: contextlib.AbstractContextManager[None]
    if not dry_run:
        vault = obsidian.Vault.main()
        maybe_lock = obsidian.snapshot_with_lock(
            vault, dry_run=dry_run, extra_msg="tidy"
        )
    else:
        maybe_lock = contextlib.nullcontext()

    with maybe_lock:
        with timehelper.print_time("sync_topics"):
            sync_topics(dry_run=dry_run)


def sync_topics(*, dry_run: bool) -> None:
    link_pattern = re.compile(r"\"?\[\[([^\]]+)\]\]\"?")

    # Parse topics from Obsidian properties in any note.
    topic_to_path_and_subheader_list_map: Dict[str, List[Tuple[pathlib.Path, str]]] = (
        defaultdict(list)
    )
    vault = obsidian.Vault.main()
    for path in vault.markdown_files():
        document = obsidian.Document.from_path(path)
        properties_map = document.properties()
        topics_list = properties_map.get("topics", [])
        if topics_list is None:
            continue

        for topic in topics_list:
            m = link_pattern.match(topic)
            if not m:
                colors.error(f"topic was not a link: {topic!r} ({path})")
                continue

            topic_to_path_and_subheader_list_map[m.group(1)].append((path, ""))

    thought_pattern = re.compile(r"###?(.+)\nTopics: (.+)")
    for path in files_with_topic_subheaders(vault):
        for full_match in thought_pattern.finditer(path.read_text()):
            subheader = full_match.group(1).strip()
            topics_str = full_match.group(2).strip().split(", ")
            for topic_str in topics_str:
                link_match = link_pattern.match(topic_str)
                if not link_match:
                    colors.error(
                        f"topic was not a link: {topic_str!r} ({subheader!r} in {path})"
                    )
                    continue

                topic_to_path_and_subheader_list_map[link_match.group(1)].append(
                    (path, subheader)
                )

    for topic, path_and_subheader_list in topic_to_path_and_subheader_list_map.items():
        update_topic(topic, path_and_subheader_list, dry_run=dry_run)


def files_with_topic_subheaders(
    vault: obsidian.Vault,
) -> Generator[pathlib.Path, None, None]:
    yield from vault.glob("*-thoughts.md")
    for p in vault.glob_regex(re.compile(r"^[0-9]{4}-[0-9]{2}\.md$")):
        if p.stem >= "2026-03":
            yield p


topic_line_pattern = lazy_re(
    r"""
    # the initial dash and any leading text
    -
    (?P<leading_text>[^\[]*)
    # the start of the link ('[[')
    \[\[
    # the target of the link
    (?P<link_target>[^|\]]+)
    # optionally, the text of the link, after a pipe
    (?:
      \|
      (?P<link_text>[^|\]]+)
    )?
    # the end of the link (']]')
    \]\]
    \s*
    # a parenthesized expression
    (?:
    \(
    (?:
    (?P<month>[A-Za-z]+\s+[0-9]+)
    ;?
    )?
    \s*
    (?:
    (?P<word_count>[0-9,]+)\s+words?
    )?
    \)
    )?
    (?P<trailing_text>.*)
    """,
    re.VERBOSE,
)


@dataclass
class TopicLink:
    leading_text: str
    link_target: str
    link_text: str
    month: Optional[datetime.date]
    word_count: Optional[int]
    trailing_text: str

    @classmethod
    def from_string(cls, s: str) -> "TopicLink":
        m = topic_line_pattern.get().match(s)
        if not m:
            raise KgError("could not parse string as topic link", s=s)

        month = map_or_none(
            m.group("month"), lambda s: datetime.datetime.strptime(s, "%b %Y").date()
        )
        return cls(
            leading_text=m.group("leading_text").lstrip(),
            link_target=m.group("link_target"),
            link_text=m.group("link_text") or "",
            month=month,
            word_count=map_or_none(
                m.group("word_count"), lambda x: int(x.replace(",", ""))
            ),
            trailing_text=m.group("trailing_text"),
        )

    @override
    def __str__(self) -> str:
        builder: List[str] = []
        builder.append("- ")
        if self.leading_text:
            builder.append(self.leading_text)

        if self.link_text:
            builder.append(f"[[{self.link_target}|{self.link_text}]]")
        else:
            builder.append(f"[[{self.link_target}]]")

        if self.month is not None or self.word_count is not None:
            builder.append(" (")
            if self.month is not None:
                builder.append(f"{self.month.strftime('%b %Y')}")
                if self.word_count is not None:
                    builder.append("; ")

            if self.word_count is not None:
                builder.append(pluralize(self.word_count, "word"))

            builder.append(")")

        builder.append(self.trailing_text)
        return "".join(builder)


@dataclass
class TopicPageSection:
    section_title: Optional[str]
    topic_link_list: List[TopicLink]

    @classmethod
    def from_section(cls, section: obsidian.Section) -> "TopicPageSection":
        topic_link_list: List[TopicLink] = []
        for line in section.content().splitlines():
            line = line.strip()
            if line.startswith("- "):
                topic_link_list.append(TopicLink.from_string(line))

        return cls(section_title=section.title(), topic_link_list=topic_link_list)

    def maybe_update_link(self, topic_link_to_update: TopicLink) -> bool:
        for topic_link in self.topic_link_list:
            if topic_link.link_target == topic_link_to_update.link_target:
                topic_link.link_text = topic_link_to_update.link_text
                topic_link.month = topic_link_to_update.month
                topic_link.word_count = topic_link_to_update.word_count
                return True

        return False

    @override
    def __str__(self) -> str:
        builder: List[str] = []
        if self.section_title is not None and len(self.section_title) > 0:
            builder.append(f"## {self.section_title}\n")

        for topic_link in self.topic_link_list:
            builder.append(str(topic_link) + "\n")

        return "".join(builder)


@dataclass
class TopicPage:
    section_list: List[TopicPageSection]

    def add_or_update_link(self, topic_link: TopicLink) -> None:
        for section in self.section_list:
            updated = section.maybe_update_link(topic_link)
            if updated:
                return

        if len(self.section_list) == 0 or (
            self.section_list[0].section_title is not None
            and self.section_list[0].section_title != ""
        ):
            self.section_list.insert(
                0, TopicPageSection(section_title=None, topic_link_list=[])
            )

        self.section_list[0].topic_link_list.insert(0, topic_link)

    @classmethod
    def from_string(cls, s: str) -> "TopicPage":
        return cls(
            section_list=[
                TopicPageSection.from_section(section)
                for section in obsidian.Document.from_text(s).sections()
                if section.title() or section.content()
            ]
        )

    @override
    def __str__(self) -> str:
        return "\n".join(map(str, self.section_list))


@dataclass
class ArticleMetadata:
    title: Optional[str]
    month: Optional[datetime.date]
    word_count: Optional[int]


def read_article_metadata(path: pathlib.Path, subheader: str) -> ArticleMetadata:
    try:
        month, _ = obsidian.split_dated_title(path.name)
    except KgError:
        month = None

    document = obsidian.Document.from_path(path)
    if subheader:
        section = document.find_section(subheader)
        if section is not None:
            word_count = section.word_count()
        else:
            word_count = None
    else:
        word_count = document.word_count()

    return ArticleMetadata(title=document.title(), month=month, word_count=word_count)


def update_topic(
    topic: str,
    path_and_subheader_list: List[Tuple[pathlib.Path, str]],
    *,
    dry_run: bool,
) -> None:
    topic_path = obsidian.Vault.main().path() / "topics" / (topic + ".md")
    if not topic_path.exists():
        original_contents = ""
        topic_page = TopicPage(section_list=[])
    else:
        original_contents = topic_path.read_text()
        topic_page = TopicPage.from_string(original_contents)

    for path, subheader in path_and_subheader_list:
        metadata = read_article_metadata(path, subheader)
        if metadata.title:
            link_text = metadata.title + (f" § {subheader}" if subheader else "")
        else:
            link_text = ""

        topic_link = TopicLink(
            leading_text="",
            link_target=path.stem + (f"#{subheader}" if subheader else ""),
            link_text=link_text,
            month=metadata.month,
            word_count=metadata.word_count,
            trailing_text="",
        )
        topic_page.add_or_update_link(topic_link)

    new_contents = str(topic_page)
    if original_contents == new_contents:
        return

    print(f"==> updating {topic_path}")
    if dry_run:
        print(githelper.make_ansi_diff(original_contents, new_contents))
    else:
        topic_path.write_text(new_contents)


cmd = command.Command.from_function(main, help="Tidy up the vault.")
