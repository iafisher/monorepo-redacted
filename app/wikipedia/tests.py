from iafisher.prelude import *
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
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="wikipedia")) > 0
        )
