from iafisher.prelude import *
from lib.testing import *

from .humanunits import parse_bytes, parse_duration, parse_time, to_bytes


class Tests(Base):
    def test_parse_time(self):
        self.assertEqual(dt.time(8, 0), parse_time("8am"))
        self.assertEqual(dt.time(8, 0), parse_time("8 am"))
        self.assertEqual(dt.time(8, 0), parse_time(" 8:00am "))
        self.assertEqual(dt.time(12, 30), parse_time("12:30pm  "))
        self.assertEqual(dt.time(13, 6), parse_time("  1:06pm"))
        self.assertEqual(dt.time(17, 43), parse_time("17:43"))
        self.assertEqual(dt.time(0, 0), parse_time("00:00"))

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
        self.assertEqual(dt.timedelta(minutes=5), parse_duration("5m"))
        self.assertEqual(dt.timedelta(seconds=10), parse_duration("10s"))
        self.assertEqual(dt.timedelta(hours=3), parse_duration(" 3h"))
        self.assertEqual(dt.timedelta(days=5), parse_duration("5d "))
        self.assertEqual(dt.timedelta(milliseconds=10), parse_duration("10ms"))

        with self.assertRaises(KgError):
            parse_duration("")

        with self.assertRaises(KgError):
            parse_duration("5")

    def test_parse_bytes(self):
        self.assertEqual(10_000, parse_bytes("10kb"))

        self.assertEqual(2_200_000_000, parse_bytes("2.2GB"))

        with self.assertRaises(KgError):
            parse_bytes("1.5b")

    def test_to_bytes(self):
        self.assertEqual("512.0 B", to_bytes(512))
        self.assertEqual("278.8 MB", to_bytes(278828723))
