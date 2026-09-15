import re
import tempfile

from iafisher.prelude import *
from lib import command
from lib.testing import *

from . import verify_links
from .main import cmd
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
            tmpdir = pathlib.Path(tmpdir)
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

    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="obsidian"),
            """\
Usage: obsidian SUBCMD

  Umbrella command for managing Obsidian.

Subcommands:

  notes           . Work with Obsidian notes.
  plugins         . Manage Obsidian plugins.
  snapshot        . Snapshot an Obsidian vault with Git.
  tidy            . Tidy up the vault.
  verify-links    . Verify that files under live/ are hard links to archive/.


------------

Usage: obsidian notes SUBCMD

  Work with Obsidian notes.

Subcommands:

  create    . Create a new note.
  rename    . Rename a note and update all links.


------------

Usage: obsidian notes create ...

  Create a new note.

Arguments:

  -title ARG                  . the title of the Markdown file (also used to infer file name, e.g., 'Some thoughts' results in '$DATE-some-thoughts.md')
  [-filename-override ARG]    . override -title for inferring file name (should not include date)
  [-preview]                  . print preview of file to be created instead of actually creating it
  [-vault ARG]                . (default: ~/Obsidian/main)


------------

Usage: obsidian notes rename ...

  Rename a note and update all links.

Arguments:

  -from- ARG
  -to ARG
  [-vault ARG]    . (default: ~/Obsidian/main)


------------

Usage: obsidian plugins SUBCMD

  Manage Obsidian plugins.

Subcommands:

  install      . Install a local plugin.
  list         . List installed plugins.
  uninstall    . Uninstall a local plugin.


------------

Usage: obsidian plugins install ...

  Install a local plugin.

Arguments:

  path
  [-dry-run]
  [-vault ARG]    . (default: ~/Obsidian/main)


------------

Usage: obsidian plugins list ...

  List installed plugins.

Arguments:

 [-local]        . only list local plugins
 [-vault ARG]    . (default: ~/Obsidian/main)


------------

Usage: obsidian plugins uninstall ...

  Uninstall a local plugin.

Arguments:

  name
  [-vault ARG]    . (default: ~/Obsidian/main)


------------

Usage: obsidian snapshot ...

  Snapshot an Obsidian vault with Git.

Arguments:

  vaults
  [-dry-run]    . Don't actually make the commit.
  [-no-push]    . Don't push to the remote.


------------

Usage: obsidian tidy ...

  Tidy up the vault.

Arguments:

 [-write]


------------

Usage: obsidian verify-links ...

  Verify that files under live/ are hard links to archive/.

Arguments:

 [-vault ARG]    . (default: ~/Obsidian/main)
""",
        )
