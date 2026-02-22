from iafisher_foundation.prelude import *
from lib.testing import *

from .humanunits import parse_bytes, parse_duration, parse_time


class Tests(Base):
    def test_parse_time(self):
        self.assertEqual(datetime.time(8, 0), parse_time("8am"))
        self.assertEqual(datetime.time(8, 0), parse_time("8 am"))
        self.assertEqual(datetime.time(8, 0), parse_time(" 8:00am "))
        self.assertEqual(datetime.time(12, 30), parse_time("12:30pm  "))
        self.assertEqual(datetime.time(13, 6), parse_time("  1:06pm"))
        self.assertEqual(datetime.time(17, 43), parse_time("17:43"))
        self.assertEqual(datetime.time(0, 0), parse_time("00:00"))

        # ambiguous times
        with self.assertRaises(KgError):
            parse_time("8")

        with self.assertRaises(KgError):
            parse_time("8:37")

        with self.assertRaises(KgError):
            parse_time("12:55")

        with self.assertRaises(KgError):
            parse_time("")

        with self.assertRaises(KgError):
            parse_time(":")

        with self.assertRaises(KgError):
            parse_time("1:2")

        with self.assertRaises(KgError):
            parse_time("1:23p")

        with self.assertRaises(KgError):
            parse_time("1:23a")

        with self.assertRaises(KgError):
            parse_time("13:23am")

        with self.assertRaises(KgError):
            parse_time("-3:23")

        with self.assertRaises(KgError):
            parse_time("24:00")

    def test_parse_duration(self):
        self.assertEqual(datetime.timedelta(minutes=5), parse_duration("5m"))
        self.assertEqual(datetime.timedelta(seconds=10), parse_duration("10s"))
        self.assertEqual(datetime.timedelta(hours=3), parse_duration(" 3h"))
        self.assertEqual(datetime.timedelta(days=5), parse_duration("5d "))
        self.assertEqual(datetime.timedelta(milliseconds=10), parse_duration("10ms"))

        with self.assertRaises(KgError):
            parse_duration("")

        with self.assertRaises(KgError):
            parse_duration("5")

    def test_parse_bytes(self):
        self.assertEqual(10_000, parse_bytes("10kb"))

        self.assertEqual(2_200_000_000, parse_bytes("2.2GB"))

        with self.assertRaises(KgError):
            parse_bytes("1.5b")
