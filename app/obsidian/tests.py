import tempfile
from pathlib import Path

from iafisher.prelude import *
from lib import command
from lib.testing import *

from .create_journal import create_journal
from .main import cmd
from .notes import create_note, format_base_filename
from .tidy import TopicLink, TopicPage, TopicPageSection

TOPIC_PAGE = """\
- important: [[golang|Go]]
- [[2025-07-zig-thoughts|Zig thoughts]] (Jul 2025)

## Dynamic languages
- [[python]] (300 words)
- [[javascript]] (Feb 2024; 200 words) -- not including typescript
"""


class Test(Base):
    def test_topic_pages(self):
        topic_link_string = (
            "- test: [[javascript]] (Feb 2024; 200 words) -- not including typescript"
        )
        topic_link = TopicLink.from_string(topic_link_string)
        self.assertEqual(
            TopicLink(
                leading_text="test: ",
                link_target="javascript",
                link_text="",
                month=dt.date(2024, 2, 1),
                word_count=200,
                trailing_text=" -- not including typescript",
            ),
            topic_link,
        )
        self.assertEqual(topic_link_string, str(topic_link))

        self.assertEqual(
            TopicLink(
                leading_text="important: ",
                link_target="golang",
                link_text="Go",
                month=None,
                word_count=None,
                trailing_text="",
            ),
            TopicLink.from_string("- important: [[golang|Go]]"),
        )

        topic_page = TopicPage.from_string(TOPIC_PAGE)
        self.assertEqual(
            TopicPage(
                section_list=[
                    TopicPageSection(
                        section_title="",
                        topic_link_list=[
                            TopicLink(
                                leading_text="important: ",
                                link_target="golang",
                                link_text="Go",
                                month=None,
                                word_count=None,
                                trailing_text="",
                            ),
                            TopicLink(
                                leading_text="",
                                link_target="2025-07-zig-thoughts",
                                link_text="Zig thoughts",
                                month=dt.date(2025, 7, 1),
                                word_count=None,
                                trailing_text="",
                            ),
                        ],
                    ),
                    TopicPageSection(
                        section_title="Dynamic languages",
                        topic_link_list=[
                            TopicLink(
                                leading_text="",
                                link_target="python",
                                link_text="",
                                month=None,
                                word_count=300,
                                trailing_text="",
                            ),
                            TopicLink(
                                leading_text="",
                                link_target="javascript",
                                link_text="",
                                month=dt.date(2024, 2, 1),
                                word_count=200,
                                trailing_text=" -- not including typescript",
                            ),
                        ],
                    ),
                ]
            ),
            topic_page,
        )

        self.assertEqual(TOPIC_PAGE, str(topic_page))

    def test_create_journal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            def replace_carets(s: str) -> str:
                # expecttest doesn't work with non-ASCII-printable characters
                return s.replace("❮", "<").replace("❯", ">")

            jul1 = dt.date(2026, 7, 2)
            jul_archive_path = create_journal(tmpdir, today=jul1)
            assert jul_archive_path is not None
            self.assertEqual(
                jul_archive_path.relative_to(tmpdir).as_posix(),
                "archive/2026/07/2026-07-01-journal.md",
            )
            self.assertExpectedInline(
                replace_carets(jul_archive_path.read_text()),
                """\
---
created-by: "human:iafisher"
---
# July 2026
< [[2026-06-01-journal|June]] | July | [[2026-08-01-journal|August]] >
""",
            )

            # Shouldn't overwrite existing path.
            archive_path_again = create_journal(tmpdir, today=jul1)
            self.assertIsNone(archive_path_again)

            # Now it is the next month, create a new journal note.
            aug1 = dt.date(2026, 8, 1)
            aug_archive_path = create_journal(tmpdir, today=aug1)
            assert aug_archive_path is not None
            self.assertEqual(
                aug_archive_path.relative_to(tmpdir).as_posix(),
                "archive/2026/08/2026-08-01-journal.md",
            )
            self.assertExpectedInline(
                replace_carets(aug_archive_path.read_text()),
                """\
---
created-by: "human:iafisher"
---
# August 2026
< [[2026-07-01-journal|July]] | August | [[2026-09-01-journal|September]] >
""",
            )

    def test_help_text(self):
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="obsidian")) > 0
        )


def create_test_note(tmpdir: Path, title: str, today: dt.date) -> Path:
    filename = format_base_filename(title)
    return create_note(tmpdir, filename, title=title, today=today)
