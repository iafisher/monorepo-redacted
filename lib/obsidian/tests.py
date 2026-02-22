import pprint

from expecttest import TestCase

from iafisher_foundation.prelude import *
from lib.testing import *

from . import journal
from .obsidian import (
    Document,
    append_to_section,
    format_month,
    is_word,
    split_dated_title,
    _update_link,
)


JOURNAL_TEXT = """\
## December 1
*Sunday*

~~Task: Back up Bitwarden to hard drive~~
Task: Christmas list

**Event**: *7 am*: Chinese lesson (Jiayun)
**Event**: *6:30 pm*: Grad school mentoring

Lorem ipsum 1

## Dec 2
*Monday -- Upstate*

Lorem ipsum 2

~~**Event**: *6 pm*: Dinner~~
- This didn't happen.

## Dec 3
*Anora* with friends after work.

## See also
- ...
"""


class Test(Base):
    def test_format_month(self):
        self.assertEqual("2025-02", format_month(datetime.date(2025, 2, 1)))
        self.assertEqual("2024-11", format_month(datetime.date(2024, 11, 15)))

    def test_split_dated_title(self):
        self.assertEqual(
            (datetime.date(2025, 4, 6), "test"), split_dated_title("2025-04-06-test")
        )
        self.assertEqual(
            (datetime.date(2025, 4, 1), "test"), split_dated_title("2025-04-test")
        )

    def test_update_link(self):
        self.assertEqual(
            "Test link: [[b]]\n",
            _update_link(
                "Test link: [[a]]\n", old_title="a", new_title="b", preserve_text=False
            ),
        )
        self.assertEqual(
            "Test link: [[b|a]]\n",
            _update_link(
                "Test link: [[a]]\n", old_title="a", new_title="b", preserve_text=True
            ),
        )
        self.assertEqual(
            "Test link: [[b|display text]]\n",
            _update_link(
                "Test link: [[a|display text]]\n",
                old_title="a",
                new_title="b",
                preserve_text=False,
            ),
        )
        # can change section title to proper link
        self.assertEqual(
            "[[2025.04 Whatever]]\n",
            _update_link(
                "[[Scratchpad#2025.04.06 Whatever]]\n",
                old_title="Scratchpad#2025.04.06 Whatever",
                new_title="2025.04 Whatever",
                preserve_text=False,
            ),
        )
        # can update link that includes section title
        self.assertEqual(
            "Test link: [[new#section|display text]]\n",
            _update_link(
                "Test link: [[old#section|display text]]\n",
                old_title="old",
                new_title="new",
                preserve_text=False,
            ),
        )
        # case-insensitive
        self.assertEqual(
            "Test link: [[B]]\n",
            _update_link(
                "Test link: [[a]]\n", old_title="A", new_title="B", preserve_text=False
            ),
        )

    def test_is_word(self):
        self.assertTrue(is_word("hello"))
        self.assertTrue(is_word("Didn't"))
        self.assertTrue(is_word("also:"))
        self.assertTrue(is_word("fire-truck"))
        self.assertTrue(is_word("look?"))
        self.assertTrue(is_word("C99"))
        self.assertTrue(is_word("*See"))
        self.assertTrue(is_word("**Don't"))
        self.assertTrue(is_word("(when"))
        self.assertTrue(is_word("`x`"))
        self.assertTrue(is_word("a"))
        self.assertTrue(is_word('"a'))
        self.assertTrue(is_word("'a"))
        self.assertTrue(is_word("a,"))
        self.assertTrue(is_word("[example](https://example.com)"))
        # a single variable name in backticks is a word, but not a whole expression
        self.assertFalse(is_word("`x"))
        self.assertFalse(is_word("-"))
        self.assertFalse(is_word("*"))
        self.assertFalse(is_word("`"))


SAMPLE_DOCUMENT = """\

---
to-publish: false
topics:
  - "[[t-science]]"
---
# Document title
<insert table of contents>

## Section 1
```python
print("Hello, world")
```

## Section 2
Lorem ipsum

## Section 3
"""


class Test2(Base, TestCase):
    def test_parse_document(self):
        document = Document.from_text(SAMPLE_DOCUMENT)
        self.assertExpectedInline(
            "\n".join(map(repr, document.blocks)),
            """\
PropertiesBlock(start=0, end=55)
HeaderBlock(start=55, end=72, title='Document title', level=1)
TextBlock(start=72, end=100)
HeaderBlock(start=100, end=113, title='Section 1', level=2)
CodeBlock(start=113, end=149)
TextBlock(start=149, end=150)
HeaderBlock(start=150, end=163, title='Section 2', level=2)
TextBlock(start=163, end=176)
HeaderBlock(start=176, end=189, title='Section 3', level=2)""",
        )
        self.assertEqual("Document title", document.title())
        self.assertExpectedInline(
            repr(document.properties()),
            """{'to-publish': False, 'topics': ['[[t-science]]']}""",
        )
        self.assertEqual(
            document.fulltext, "".join(b.content() for b in document.blocks)
        )

        self.assertExpectedInline(
            "\n".join(map(repr, document.sections())),
            """\
Section(header=None, blocks=[TextBlock(start=72, end=100)])
Section(header=HeaderBlock(start=100, end=113, title='Section 1', level=2), blocks=[CodeBlock(start=113, end=149), TextBlock(start=149, end=150)])
Section(header=HeaderBlock(start=150, end=163, title='Section 2', level=2), blocks=[TextBlock(start=163, end=176)])
Section(header=HeaderBlock(start=176, end=189, title='Section 3', level=2), blocks=[])""",
        )

    def test_append_to_section(self):
        document = Document.from_text(SAMPLE_DOCUMENT)
        self.assertExpectedInline(
            append_to_section(
                document,
                section_title="Section 1",
                content="hello world",
                create_if_missing=False,
            ),
            """\
<insert table of contents>

## Section 1
```python
print("Hello, world")
```
hello world

## Section 2
Lorem ipsum

## Section 3
""",
        )

        self.assertExpectedInline(
            append_to_section(
                document,
                section_title="A new section",
                content="hello world",
                create_if_missing=True,
            ),
            """\
<insert table of contents>

## Section 1
```python
print("Hello, world")
```

## Section 2
Lorem ipsum

## Section 3

## A new section
hello world""",
        )

    def test_read_journal_sections(self):
        document = Document.from_text(JOURNAL_TEXT)
        entries = list(journal.entries(document))
        self.assertExpectedInline(
            pprint.pformat(entries),
            """\
[Entry(title='December 1',
       subheader=None,
       events=[Event(text='Chinese lesson (Jiayun)',
                     time_of_day=datetime.time(7, 0),
                     canceled=False),
               Event(text='Grad school mentoring',
                     time_of_day=datetime.time(18, 30),
                     canceled=False)],
       tasks=[Task(text='Back up Bitwarden to hard drive', finished=True),
              Task(text='Christmas list', finished=False)]),
 Entry(title='Dec 2',
       subheader=None,
       events=[Event(text='Dinner',
                     time_of_day=datetime.time(18, 0),
                     canceled=True)],
       tasks=[]),
 Entry(title='Dec 3', subheader=None, events=[], tasks=[])]""",
        )
