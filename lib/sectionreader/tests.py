from lib.testing import *

from .sectionreader import look_for_end_text, look_for_start_text


class Test(Base):
    def test_look_for_end(self):
        sections = list(
            look_for_end_text(
                TEXT1, lambda line: line.isspace(), exclusive=True, keep_ends=True
            )
        )
        self.assertEqual(3, len(sections))
        self.assertEqual(["United States\n", "Washington DC\n"], sections[0])
        self.assertEqual(["Canada\n", "Ottawa\n"], sections[1])
        self.assertEqual(["Mexico\n", "Mexico City\n"], sections[2])

        sections = list(
            look_for_end_text(
                TEXT1, lambda line: line.isspace(), exclusive=False, keep_ends=True
            )
        )
        self.assertEqual(3, len(sections))
        self.assertEqual(["United States\n", "Washington DC\n", "\n"], sections[0])
        self.assertEqual(["Canada\n", "Ottawa\n", "\n"], sections[1])
        self.assertEqual(["Mexico\n", "Mexico City\n"], sections[2])

        # Should be able to recover exact text of original
        sections = list(
            look_for_end_text(
                TEXT1, lambda line: line.isspace(), exclusive=False, keep_ends=True
            )
        )
        self.assertEqual(TEXT1, "".join("".join(sec) for sec in sections))

    def test_look_for_start(self):
        sections = list(
            look_for_start_text(
                TEXT2,
                lambda line: line.startswith("##"),
                exclusive=False,
                keep_init=True,
                keep_ends=False,
            )
        )
        self.assertEqual(3, len(sections))
        self.assertEqual(["Table of contents", ""], sections[0])
        self.assertEqual(["## Header 1", "- Lorem", "    - ipsum", ""], sections[1])
        self.assertEqual(["## Header 2"], sections[2])

        sections = list(
            look_for_start_text(
                TEXT2,
                lambda line: line.startswith("##"),
                exclusive=True,
                keep_init=False,
                keep_ends=False,
            )
        )
        self.assertEqual(1, len(sections))
        self.assertEqual(["- Lorem", "    - ipsum", ""], sections[0])
        # Empty section is dropped with `exclusive=True`

        # Should be able to recover exact text of original
        sections = list(
            look_for_start_text(
                TEXT2,
                lambda line: line.startswith("##"),
                exclusive=False,
                keep_init=True,
                keep_ends=True,
            )
        )
        self.assertEqual(TEXT2, "".join("".join(sec) for sec in sections))


TEXT1 = """\
United States
Washington DC

Canada
Ottawa

Mexico
Mexico City
"""

TEXT2 = """\
Table of contents

## Header 1
- Lorem
    - ipsum

## Header 2
"""
