from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd, parse_one_line
from .models import Book


class Test(Base):
    def test_parse_one_line(self):
        # linked title
        book = parse_one_line(
            "1. *[[2025.01 The Collapse of Complex Societies|The Collapse of Complex Societies]]* by Joseph A. Tainter (Jan 8–10, 216 pp.)",
            note_year=2025,
        )
        self.assertEqual(
            Book(
                title="The Collapse of Complex Societies",
                author="Joseph A. Tainter",
                date_started=datetime.date(2025, 1, 8),
                date_finished=datetime.date(2025, 1, 10),
                pages=216,
            ),
            book,
        )

        # no link, start and end date the same
        book = parse_one_line(
            "19. *Ghosts* by Paul Auster (Jun 2, 74 pp.)",
            note_year=2025,
        )
        self.assertEqual(
            Book(
                title="Ghosts",
                author="Paul Auster",
                date_started=datetime.date(2025, 6, 2),
                date_finished=datetime.date(2025, 6, 2),
                pages=74,
            ),
            book,
        )

        # '+' rating at beginning, start and end months different
        book = parse_one_line(
            "21. + *[[B2024.05 The Critic's Hornbook|The Critic's Hornbook]]* by William C. Dowling (May 16 – Jun 8, 177 pp.)",
            note_year=2024,
        )

        self.assertEqual(
            Book(
                title="The Critic's Hornbook",
                author="William C. Dowling",
                date_started=datetime.date(2024, 5, 16),
                date_finished=datetime.date(2024, 6, 8),
                pages=177,
            ),
            book,
        )

        # started and finished in different years
        book = parse_one_line(
            "67. ++ *[[B2023.12 Central Banking 101|Central Banking 101]]* by Joseph J. Wang (Dec 29 – Jan 2, 225 pp.)",
            note_year=2023,
        )

        self.assertEqual(
            Book(
                title="Central Banking 101",
                author="Joseph J. Wang",
                date_started=datetime.date(2023, 12, 29),
                date_finished=datetime.date(2024, 1, 2),
                pages=225,
            ),
            book,
        )

        # star rating at the end
        book = parse_one_line(
            "5. *[[B2022.01 Against the Day|Against the Day]]* by Thomas Pynchon (Jan 21 – Mar 24, 1085 pp.) ★★★★",
            note_year=2022,
        )

        self.assertEqual(
            Book(
                title="Against the Day",
                author="Thomas Pynchon",
                date_started=datetime.date(2022, 1, 21),
                date_finished=datetime.date(2022, 3, 24),
                pages=1085,
            ),
            book,
        )

        # no page length
        book = parse_one_line(
            "37. +++ *[[B2024.10 Anna Karenina|Anna Karenina]]* by Leo Tolstoy (Oct 1 – Nov 26)",
            note_year=2024,
        )

        self.assertEqual(
            Book(
                title="Anna Karenina",
                author="Leo Tolstoy",
                date_started=datetime.date(2024, 10, 1),
                date_finished=datetime.date(2024, 11, 26),
                pages=None,
            ),
            book,
        )

        # editor
        book = parse_one_line(
            "15. *[[B2023.04 The Best American Short Stories 2014|The Best American Short Stories 2014]]* by Jennifer Egan (ed.) (Apr 1–14, 325 pp.)",
            note_year=2023,
        )

        self.assertEqual(
            Book(
                title="The Best American Short Stories 2014",
                author="Jennifer Egan (ed.)",
                date_started=datetime.date(2023, 4, 1),
                date_finished=datetime.date(2023, 4, 14),
                pages=325,
            ),
            book,
        )

        # parenthetical comment
        book = parse_one_line(
            "22. *[[B2024.06 Text and Corpus Analysis|Text and Corpus Analysis]]* by Michael Stubbs (Jun 1, skimmed)",
            note_year=2024,
        )

        self.assertEqual(
            Book(
                title="Text and Corpus Analysis",
                author="Michael Stubbs",
                date_started=datetime.date(2024, 6, 1),
                date_finished=datetime.date(2024, 6, 1),
                pages=None,
            ),
            book,
        )

        # negative rating
        book = parse_one_line(
            "39. - *Breakneck: China's Quest to Engineer the Future* by Dan Wang (Oct 5–14)",
            note_year=2025,
        )

        self.assertEqual(
            Book(
                title="Breakneck: China's Quest to Engineer the Future",
                author="Dan Wang",
                date_started=datetime.date(2025, 10, 5),
                date_finished=datetime.date(2025, 10, 14),
                pages=None,
            ),
            book,
        )

    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="books"),
            """\
Usage: books SUBCMD

  Manage books database.

Subcommands:

  list    . List books.
  sync    . Sync with Obsidian log.


------------

Usage: books list ...

  List books.

Arguments:

 [-year ARG]


------------

Usage: books sync ...

  Sync with Obsidian log.

Arguments:

 [-quiet]    . print less output
 [-write]    . write to database instead of doing a dry run
""",
        )
