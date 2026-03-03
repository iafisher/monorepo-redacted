from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd
from .tidy import tidy_regex


class Test(Base):
    def test_tidy_regex_en_dashes(self):
        self.assertExpectedInline(
            tidy_regex("where they pushed their majority to 30-22"),
            """where they pushed their majority to 30–22""",
        )
        # don't replace inside of <ref>...</ref>
        self.assertExpectedInline(
            tidy_regex("<ref name=:0>{{cite web |date = 2025-01-01}}</ref>"),
            """<ref name=:0>{{cite web |date = 2025-01-01}}</ref>""",
        )
        # don't replace inside of file name
        self.assertExpectedInline(
            tidy_regex("[[File:Snapshot-2025-01-01.jpg]]"),
            """[[File:Snapshot-2025-01-01.jpg]]""",
        )
        # don't replace inside of a template
        self.assertExpectedInline(
            tidy_regex("{{cite web |date = 2025-01-01}}"),
            """{{cite web |date = 2025-01-01}}""",
        )

    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="wikipedia"),
            """\
Usage: wikipedia SUBCMD

Subcommands:

  llmapedia
  serve        . Run the webserver.
  tidy


------------

Usage: wikipedia llmapedia SUBCMD

Subcommands:

  export


------------

Usage: wikipedia llmapedia export ...

Arguments:

  -dest ARG
  -vital-list ARG


------------

Usage: wikipedia serve ...

  Run the webserver.

Arguments:

 [-debug]       . Run the server in debug mode.
 [-port ARG]    . (default: 7800)
 [-testdb]      . Run against the test database.


------------

Usage: wikipedia tidy SUBCMD

Subcommands:

  nightly
  test


------------

Usage: wikipedia tidy nightly ...

Arguments:

 [-article ARG]      . copy-edit this article
 [-category ARG]     . fetch a random article in this category
 [-model ARG]        . (default: 'gpt-5.2')
 [-vital-level-3]    . fetch a random level 3 vital article


------------

Usage: wikipedia tidy test ...

Arguments:

  article
  [-model ARG]       . (default: 'claude-haiku-4-5')
  [-regex]           . use regex instead of an LLM
  [-revision ARG]    . fetch this revision of the page instead of the latest revision
  [-save ARG]        . save the raw wikitext output to this file
""",
        )
