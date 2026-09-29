import re
import tempfile
from pathlib import Path

from iafisher.prelude import *
from lib import command
from lib.testing import *

from . import verify_links
from .create_journal import create_journal
from .main import cmd
from .notes import create_note, format_base_filename
from .sweep import main as main_sweep
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

    def test_verify_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "live" / "subdir").mkdir(parents=True)
            (tmpdir / "archive" / "2026" / "09").mkdir(parents=True)

            ok_path = tmpdir / "archive" / "2026" / "09" / "2026-09-12-ok.md"
            ok_path.write_text(
                "---\narchive-path: archive/2026/09/2026-09-12-ok.md\n---\n"
            )
            os.link(ok_path, (tmpdir / "live" / "ok.md"))

            (tmpdir / "live" / "skip.md").write_text(
                "This file has no archive-path property.\n"
            )

            (tmpdir / "live" / "subdir" / "fail-not-found.md").write_text(
                "---\narchive-path: archive/fail-not-found.md\n---\n"
            )

            fail_not_link_contents = (
                "---\narchive-path: archive/2026/09/2026-09-12-fail-not-link.md\n---\n"
            )
            (
                tmpdir / "archive" / "2026" / "09" / "2026-09-12-fail-not-link.md"
            ).write_text(fail_not_link_contents)
            (tmpdir / "live" / "subdir" / "fail-not-link.md").write_text(
                fail_not_link_contents
            )

            stdout = self.capture_stdout(lambda: verify_links._verify(tmpdir))
            self.assertExpectedInline(
                re.sub(r" [0-9]+ ", " <redacted> ", stdout),
                """\
PASS: live/ok.md
SKIP: live/skip.md
FAIL: live/subdir/fail-not-found.md (archive/fail-not-found.md not found)
FAIL: live/subdir/fail-not-link.md (inode mismatch: <redacted> != <redacted> archive/2026/09/2026-09-12-fail-not-link.md)
""",
            )

    def test_sweep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            today = dt.date(2026, 8, 1)

            def days_ago(n: int) -> dt.date:
                return today - dt.timedelta(days=n)

            create_test_note(tmpdir, "to-be-swept", days_ago(15))
            create_test_note(tmpdir, "not-yet-swept", days_ago(14))

            stdout, stderr = self.capture_output(
                lambda: main_sweep(vault=tmpdir, dry_run=True, date=today)
            )
            self.assertExpectedInline(stderr, """""")
            self.assertExpectedInline(
                stdout,
                """\
live/to-be-archived/2026-07-17-to-be-swept.md
""",
            )

            # Dry run, no files deleted yet
            d = tmpdir / "live" / "to-be-archived"
            self.assertExpectedInline(
                repr(os.listdir(d)),
                """['2026-07-17-to-be-swept.md', '2026-07-18-not-yet-swept.md']""",
            )

            main_sweep(vault=tmpdir, dry_run=False, date=today)

            self.assertExpectedInline(
                repr(os.listdir(d)),
                """['2026-07-18-not-yet-swept.md']""",
            )

            # Archive path missing
            archive_path, _ = create_test_note(tmpdir, "broken-1", days_ago(15))
            archive_path.unlink()

            # Not a hard link
            _, live_path = create_test_note(tmpdir, "broken-2", days_ago(15))
            tmp_path = tmpdir / "tmp"
            tmp_path.write_text(live_path.read_text())
            # This replaces the live path with a new inode, no longer a hard link to the archive path.
            tmp_path.rename(live_path)

            stdout, stderr = self.capture_output(
                lambda: main_sweep(vault=tmpdir, dry_run=True, date=today)
            )
            self.assertExpectedInline(
                stdout,
                """""",
            )
            self.assertExpectedInline(
                stderr,
                """\
archive path archive/2026/07/2026-07-17-broken-1.md does not exist for live/to-be-archived/2026-07-17-broken-1.md
live/to-be-archived/2026-07-17-broken-2.md is not a hard link to archive path archive/2026/07/2026-07-17-broken-2.md
""",
            )

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
            live_path = tmpdir / "live" / "journal.md"
            self.assertTrue(live_path.exists())
            self.assertEqual(live_path.stat().st_ino, jul_archive_path.stat().st_ino)
            self.assertExpectedInline(
                replace_carets(live_path.read_text()),
                """\
---
date-created: "2026-07-01"
archive-path: "archive/2026/07/2026-07-01-journal.md"
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
            self.assertEqual(live_path.stat().st_ino, aug_archive_path.stat().st_ino)
            # Live path is replaced with August note.
            self.assertExpectedInline(
                replace_carets(live_path.read_text()),
                """\
---
date-created: "2026-08-01"
archive-path: "archive/2026/08/2026-08-01-journal.md"
created-by: "human:iafisher"
---
# August 2026
< [[2026-07-01-journal|July]] | August | [[2026-09-01-journal|September]] >
""",
            )
            # Archive path for July is untouched.
            self.assertExpectedInline(
                replace_carets(jul_archive_path.read_text()),
                """\
---
date-created: "2026-07-01"
archive-path: "archive/2026/07/2026-07-01-journal.md"
created-by: "human:iafisher"
---
# July 2026
< [[2026-06-01-journal|June]] | July | [[2026-08-01-journal|August]] >
""",
            )

    def test_help_text(self):
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="obsidian")) > 0
        )


def create_test_note(tmpdir: Path, title: str, today: dt.date) -> Tuple[Path, Path]:
    filename = format_base_filename(title)
    return create_note(tmpdir, filename, title=title, today=today)
