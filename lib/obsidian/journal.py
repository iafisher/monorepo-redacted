from iafisher_foundation.prelude import *
from lib import humanunits

from .obsidian import Document, Section


@dataclass
class Event:
    text: str
    time_of_day: datetime.time
    canceled: bool


@dataclass
class Task:
    text: str
    finished: bool


@dataclass
class Entry:
    title: str
    subheader: Optional[str]
    events: List[Event]
    tasks: List[Task]
    section: Section = dataclasses.field(repr=False)


_title_pattern = lazy_re(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", flags=re.IGNORECASE
)


def entries(document: Document) -> Generator[Entry, None, None]:
    rgx = _title_pattern.get()
    for section in document.sections():
        if section.header is not None and rgx.match(section.header.title):
            yield _parse_section(section.header.title, section)


_subheader_pattern = lazy_re(
    r"^\*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?: – (.+))?\*$",
    flags=re.IGNORECASE,
)
_event_pattern = lazy_re(r"(~~)?\*\*Event(?:\*\*:|:\*\*) \*([^\*]+)\*: (.+)")


def _parse_section(title: str, section: Section) -> Entry:
    # TODO(2025-12): Rewrite using obsidian2.Document
    contents = section.content()

    subheader = None
    start_of_content = None
    events: List[Event] = []
    tasks: List[Task] = []

    for i, line in enumerate(contents.splitlines()):
        if start_of_content is None and not line or line.isspace():
            continue

        if i == 0:
            m = _subheader_pattern.get().match(line)
            if m:
                subheader = m.group(2)
                continue

        if start_of_content is None:
            start_of_content = i

        m = _event_pattern.get().match(line)
        if m is not None:
            canceled = m.group(1) is not None
            text = m.group(3)
            if canceled:
                text = text.rstrip("~")

            events.append(
                Event(
                    text=text,
                    time_of_day=humanunits.parse_time(m.group(2)),
                    canceled=canceled,
                )
            )
        elif line.startswith("Task:"):
            text = line.split(":", maxsplit=1)[1].strip()
            tasks.append(Task(text=text, finished=False))
        elif line.startswith("~~Task:") and line.endswith("~~"):
            text = line.split(":", maxsplit=1)[1].rstrip("~").strip()
            tasks.append(Task(text=text, finished=True))

    return Entry(
        title=title,
        subheader=subheader,
        events=events,
        tasks=tasks,
        section=section,
    )
