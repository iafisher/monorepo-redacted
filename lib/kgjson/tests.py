import json
import tempfile
from typing import Literal, Self

from expecttest import TestCase

from iafisher_foundation.timehelper import TZ_NYC
from iafisher_foundation.prelude import *
from lib.testing import *

from . import kgjson


@dataclass
class Author(kgjson.Base):
    first_name: str
    last_name: str
    date_of_birth: Optional[datetime.date] = None


@dataclass
class Book(kgjson.Base):
    title: str
    author: Author
    year: Optional[int]


@dataclass
class Bookshelf(kgjson.Base):
    books: List[Book] = dataclasses.field(default_factory=list)


@dataclass
class WithTimestamp(kgjson.Base):
    timestamp: datetime.datetime


@dataclass
class WithTimeOfDay(kgjson.Base):
    time_of_day: datetime.time


@dataclass
class AppState(kgjson.Base):
    magic_number: int = 42


VALIDATION_MESSAGE = "there must be at least one number"


@dataclass
class ExampleInnerWithValidation(kgjson.Base):
    numbers: List[int]

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        if len(o.numbers) == 0:
            raise KgError(VALIDATION_MESSAGE)


@dataclass
class ExampleOuterWithValidation(kgjson.Base):
    inner: ExampleInnerWithValidation


# adapted from app/jobserver


@dataclass
class JobserverJobStats(kgjson.Base):
    wall_time_secs: float
    user_time_secs: float
    system_time_secs: float
    max_memory: int


@dataclass
class JobserverJob(kgjson.Base):
    name: str
    last_stats: Optional[JobserverJobStats] = None
    extra_pythonpath: Optional[List[str]] = None


@dataclass
class JobserverState(kgjson.Base):
    jobs: List[JobserverJob]


def make_example():
    return dict(
        books=[
            dict(
                title="Underworld",
                author=dict(first_name="Don", last_name="DeLillo"),
                year=1997,
            )
        ]
    )


class Test(Base, TestCase):
    def test_deserialize(self):
        example = make_example()

        author = Author.deserialize(example["books"][0]["author"])  # type: ignore
        self.assertEqual("Don", author.first_name)
        self.assertEqual("DeLillo", author.last_name)

        book = Book.deserialize(example["books"][0])
        self.assertEqual(author, book.author)
        self.assertEqual("Underworld", book.title)
        self.assertEqual(1997, book.year)

        bookshelf = Bookshelf.deserialize(example)
        self.assertEqual(1, len(bookshelf.books))

    def test_deserialize_date(self):
        author = Author.deserialize(
            dict(first_name="Thomas", last_name="Pynchon", date_of_birth="1937-05-08")
        )
        self.assertEqual(datetime.date(1937, 5, 8), author.date_of_birth)

        with self.assertRaises(KgError) as cm:
            Author.deserialize(
                dict(first_name="Thomas", last_name="Pynchon", date_of_birth="5/8/1937")
            )

        self.assertEqual("5/8/1937", cm.exception.val("value"))

    def test_deserialize_timestamp(self):
        o = WithTimestamp.deserialize(dict(timestamp=1736031348))
        self.assertEqual(
            datetime.datetime(2025, 1, 4, 17, 55, 48, tzinfo=TZ_NYC), o.timestamp
        )

        o = WithTimestamp.deserialize(dict(timestamp="2025-01-04 17:55:48-05:00"))
        self.assertEqual(
            datetime.datetime(2025, 1, 4, 17, 55, 48, tzinfo=TZ_NYC), o.timestamp
        )

        with self.assertRaises(KgError):
            # refuse to deserialize datetimes without time-zone info
            WithTimestamp.deserialize(dict(timestamp="2025-01-04 17:55:48"))

    def test_deserialize_time_of_day(self):
        o = WithTimeOfDay.deserialize(dict(time_of_day="08:30"))
        self.assertEqual(datetime.time(8, 30), o.time_of_day)

    def test_deserialize_optional_dict(self):
        o = JobserverState.deserialize(
            {
                "jobs": [
                    {
                        "name": "testjob",
                        "last_stats": None,
                        "extra_pythonpath": None,
                    },
                ]
            }
        )
        self.assertEqual(1, len(o.jobs))
        self.assertEqual("testjob", o.jobs[0].name)
        self.assertEqual(None, o.jobs[0].last_stats)
        self.assertEqual(None, o.jobs[0].extra_pythonpath)

    def test_deserialize_missing_key(self):
        example = make_example()
        del example["books"][0]["author"]["last_name"]  # type: ignore

        with self.assertRaises(KgError) as cm:
            Bookshelf.deserialize(example)

        self.assertEqual("last_name", cm.exception.val("key"))
        self.assertEqual("$.books[0].author.last_name", cm.exception.val("json_path"))

    def test_deserialize_missing_key_with_default(self):
        example = make_example()
        del example["books"][0]["year"]

        bookshelf = Bookshelf.deserialize(example)
        self.assertEqual(None, bookshelf.books[0].year)

    def test_deserialize_missing_key_with_default_factory(self):
        bookshelf = Bookshelf.deserialize(dict())
        self.assertEqual([], bookshelf.books)

    def test_deserialize_wrong_type(self):
        example = make_example()
        example["books"][0]["year"] = "N/A"

        with self.assertRaises(KgError) as cm:
            Bookshelf.deserialize(example)

        self.assertEqual("N/A", cm.exception.val("value"))
        self.assertEqual(int, cm.exception.val("expected_type"))
        self.assertEqual("$.books[0].year", cm.exception.val("json_path"))

        example = make_example()
        example["books"][0]["author"] = "Don DeLillo"

        with self.assertRaises(KgError) as cm:
            Bookshelf.deserialize(example)

        self.assertEqual("Don DeLillo", cm.exception.val("value"))
        self.assertEqual(Author, cm.exception.val("expected_type"))
        self.assertEqual("$.books[0].author", cm.exception.val("json_path"))

        with self.assertRaises(KgError) as cm:
            Bookshelf.deserialize(None)  # type: ignore

        self.assertEqual(None, cm.exception.val("value"))
        self.assertEqual(Bookshelf, cm.exception.val("expected_type"))
        self.assertEqual("$", cm.exception.val("json_path"))

    def test_deserialize_validation(self):
        d = dict(inner=dict(numbers=[]))
        with self.assertRaises(KgError) as cm:
            ExampleOuterWithValidation.deserialize(d)

        self.assertEqual(VALIDATION_MESSAGE, cm.exception.args[0])
        self.assertEqual("$.inner", cm.exception.val("json_path"))

        ExampleOuterWithValidation.deserialize(d, validate=False)

    def test_deserialize_camel_case(self):
        d = dict(firstName="Don", lastName="DeLillo", dateOfBirth="1936-11-20")
        author = Author.deserialize(d, camel_case=True)
        self.assertEqual("DeLillo", author.last_name)

    def test_deserialize_extra_key(self):
        d = dict(first_name="Philip", last_name="Roth", nationality="American")
        author = Author.deserialize(d)
        self.assertEqual("Philip", author.first_name)
        self.assertEqual("Roth", author.last_name)

    def test_literal_annotation(self):
        @dataclass
        class Example(kgjson.Base):
            time_of_day: Literal["morning", "evening"]

        example = Example.deserialize({"time_of_day": "morning"})
        self.assertExpectedInline(
            repr(example),
            """Test.test_literal_annotation.<locals>.Example(time_of_day='morning')""",
        )

        with self.assertRaises(KgError):
            Example.deserialize({"time_of_day": "afternoon"})

        example = Example(time_of_day="morning")
        self.assertExpectedInline(example.serialize(), """{"time_of_day": "morning"}""")

    def test_dict_field(self):
        @dataclass
        class Example(kgjson.Base):
            last_updated: Dict[str, datetime.datetime]

        example = Example.deserialize(
            {"last_updated": {"foo": "2025-01-01T00:00:00-05:00", "bar": 1771728968}}
        )
        self.assertExpectedInline(
            repr(example),
            """Test.test_dict_field.<locals>.Example(last_updated={'foo': datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=68400))), 'bar': datetime.datetime(2026, 2, 21, 21, 56, 8, tzinfo=zoneinfo.ZoneInfo(key='America/New_York'))})""",
        )

        with self.assertRaises(KgError):
            Example.deserialize({"last_updated": {1: 1771728968}})

    def test_with_lock(self):
        old_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                with AppState.with_lock("test.lock") as lock_file:
                    state = lock_file.read()
                    self.assertEqual(42, state.magic_number)
                    state.magic_number = 123
                    lock_file.write(state)

                with AppState.with_lock("test.lock") as lock_file:
                    state = lock_file.read()
                    self.assertEqual(123, state.magic_number)
        finally:
            os.chdir(old_cwd)

    def test_snake_to_camel(self):
        self.assertEqual("messageId", kgjson.snake_to_camel("message_id"))
        self.assertExpectedInline(
            json.dumps(
                kgjson._snake_to_camel_dict(
                    dict(all_messages=[dict(message_id=123), dict(message_id=456)])
                ),
                indent=2,
            ),
            """\
{
  "allMessages": [
    {
      "messageId": 123
    },
    {
      "messageId": 456
    }
  ]
}""",
        )
