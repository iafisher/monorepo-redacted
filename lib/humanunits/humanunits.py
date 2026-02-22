import calendar
import math
from decimal import Decimal
from iafisher_foundation.prelude import *

_time_pattern = lazy_re(
    r"^\s*([0-9]{1,2})(:[0-9]{2})?(:[0-9]{2})?\s*(am|pm)?\s*$", re.IGNORECASE
)


def parse_time(s: str) -> datetime.time:
    """
    Parse a time string, e.g., '11am', into a `datetime.time` object.
    """
    m = _time_pattern.get().match(s)
    if m is not None:
        hour_string = m.group(1)
        hour = int(hour_string)
        if m.group(2) is not None:
            minute = int(m.group(2)[1:])
        else:
            minute = 0

        if m.group(3) is not None:
            second = int(m.group(3)[1:])
        else:
            second = 0

        am_pm = (m.group(4) or "").lower()

        if not (
            # a time string is unambiguous if it...
            # ...contains AM/PM
            am_pm
            # ...starts with '0'
            or (hour_string[0] == "0")
            # ...has an hour greater than 12
            or hour > 12
        ):
            raise KgError("cannot determine if time is AM or PM", string=s)

        if minute > 59:
            raise KgError("minute cannot exceed 59", string=s, minute=minute)

        if am_pm:
            if hour > 12:
                raise KgError(
                    "hour cannot exceed 12 if AM/PM is given", string=s, hour=hour
                )
        else:
            if hour > 23:
                raise KgError("hour cannot exceed 23", string=s, hour=hour)

        if am_pm == "pm" and hour < 12:
            hour += 12

        return datetime.time(hour, minute, second)
    else:
        raise KgError("could not parse string as time", string=s)


_duration_pattern = lazy_re(r"^\s*([0-9]+)(ms|s|m|h|d)\s*$", re.IGNORECASE)


def parse_duration(s: str) -> datetime.timedelta:
    """
    Parse a string like '30m' into a `datetime.timedelta` object.
    """
    m = _duration_pattern.get().match(s)
    if m is not None:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "ms":
            return datetime.timedelta(milliseconds=n)
        elif unit == "s":
            return datetime.timedelta(seconds=n)
        elif unit == "m":
            return datetime.timedelta(minutes=n)
        elif unit == "h":
            return datetime.timedelta(hours=n)
        elif unit == "d":
            return datetime.timedelta(days=n)
        else:
            raise KgError("unknown unit for time duration", string=s, unit=unit)
    else:
        raise KgError("could not parse string as duration", string=s)


_bytes_pattern = lazy_re(r"^\s*([0-9.]+)(b|kb|mb|gb|tb)\s*$", re.IGNORECASE)


_bytes_units = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
}


def parse_bytes(s: str) -> int:
    """
    Parse a string like '5kb' into an integer number of bytes.
    """
    m = _bytes_pattern.get().match(s)
    if m is not None:
        value = Decimal(m.group(1))
        unit = m.group(2).lower()
        multiplier = _bytes_units[unit]
        value = value * multiplier
        floored = math.floor(value)
        if value != floored:
            raise KgError("bytes value is not a whole number", string=s)
        return floored
    else:
        raise KgError("could not parse string as bytes", string=s)


def month_to_int(month: str) -> int:
    """
    Parse the English name of a month (full or abbreviated) into its ordinal (January is 1).
    """
    month = month.lower()
    for i, full_month_name in enumerate(calendar.month_name):
        if not full_month_name:
            # `calendar.month_name[0]` is the empty string.
            continue
        elif full_month_name.lower().startswith(month):
            return i

    raise KgError("unrecognized month name or abbreviation", month=month)


def parse_day_of_week(s: str) -> int:
    """
    Parse the English name of a day of the week (full or abbreviated) into its ordinal (Monday is 0)
    """
    s = s.lower()
    for i, day_name in enumerate(calendar.day_name):
        if s == day_name.lower():
            return i

    for i, day_abbr in enumerate(calendar.day_abbr):
        if s == day_abbr.lower():
            return i

    raise KgError("unrecognized day of the week name or abbreviation", string=s)
