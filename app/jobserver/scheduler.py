"""
The jobserver supports four discrete schedule types:

- hourly (run every X minutes)
- daily (run at fixed times of day)
- weekly (run on fixed days of the week)
- monthly (run on fixed days of the month)

The scheduler is a pure function that takes the current time and returns the
next scheduled time.

Key observations:

- Every schedule divides the timeline into repeating intervals. Daily into days,
  weekly into weeks, etc.
- It is easy to map an absolute point in time to its interval.
- It is easy to calculate the list of scheduled times for an interval.
- For any point in time, the next scheduled time lies either in the current
  interval or the next one.

Given this, a generic implementation of `get_next_scheduled_time` is simply:

1. Calculate the current and next intervals and the list of scheduled times for
   each.
2. Return the first time from the list that is greater than the current time.
"""

from abc import ABC, abstractmethod
from typing import Self

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import humanunits, kgjson


Tzinfo = Optional[datetime.tzinfo]


class BaseSchedule(ABC):
    def get_next_scheduled_time(self, now: datetime.datetime) -> datetime.datetime:
        """
        Returns the next scheduled time greater than `now`.
        """
        tz = now.tzinfo
        this_interval = self.get_interval(now)
        next_interval = self.get_next_interval(now)
        scheduled_times = self.get_times(this_interval, tz) + self.get_times(
            next_interval, tz
        )
        r = find_first(scheduled_times, lambda x: x > now)
        assert r is not None
        return r

    @abstractmethod
    def get_interval(self, now: datetime.datetime) -> datetime.date:
        """
        Returns the first date of the interval of the schedule to which `now` belongs.

        For instance, `WeeklySchedule.get_interval` returns the Monday of the week.
        """
        pass

    @abstractmethod
    def get_next_interval(self, now: datetime.datetime) -> datetime.date:
        """
        Returns the first date of the next interval after the `now`'s interval.

        For instance, `WeeklySchedule.get_interval` returns the Monday of the next week.
        """
        pass

    @abstractmethod
    def get_times(
        self, start_of_interval: datetime.date, tzinfo: Tzinfo
    ) -> List[datetime.datetime]:
        """
        Returns all scheduled times within the interval, sorted in ascending order.

        All times should be in the timezone `tzinfo`.
        """
        pass


combine = datetime.datetime.combine


def mins(n: int) -> datetime.timedelta:
    return datetime.timedelta(minutes=n)


def days(n: int) -> datetime.timedelta:
    return datetime.timedelta(days=n)


@dataclass
class HourlySchedule(kgjson.Base, BaseSchedule):
    interval_mins: int
    start_time_of_day: datetime.time = datetime.time(0, 0)
    end_time_of_day: datetime.time = datetime.time(23, 59)
    days_of_week: List[str] = dataclasses.field(default_factory=list)

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        if o.start_time_of_day > o.end_time_of_day:
            raise KgError("start_time_of_day must be less than end_time_of_day", o=o)

    @override
    def get_interval(self, now: datetime.datetime) -> datetime.date:
        return timehelper.start_of_week(now.date())

    @override
    def get_next_interval(self, now: datetime.datetime) -> datetime.date:
        return self.get_interval(now) + days(7)

    @override
    def get_times(
        self, start_of_week: datetime.date, tzinfo: Tzinfo
    ) -> List[datetime.datetime]:
        if len(self.days_of_week) > 0:
            days_of_week = sorted(
                humanunits.parse_day_of_week(s) for s in self.days_of_week
            )
        else:
            days_of_week = list(range(0, 7))
        r: List[datetime.datetime] = []
        for day_of_week in days_of_week:
            date = start_of_week + days(day_of_week)
            t = combine(date, self.start_time_of_day, tzinfo)
            end = combine(date, self.end_time_of_day, tzinfo)
            interval = datetime.timedelta(minutes=self.interval_mins)

            while t <= end:
                r.append(t)
                t += interval

        return r


@dataclass
class DailySchedule(kgjson.Base, BaseSchedule):
    times_of_day: List[datetime.time]

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        if len(o.times_of_day) == 0:
            raise KgError("times_of_day cannot be empty", o=o)

    @override
    def get_interval(self, now: datetime.datetime) -> datetime.date:
        return now.date()

    @override
    def get_next_interval(self, now: datetime.datetime) -> datetime.date:
        return now.date() + days(1)

    @override
    def get_times(self, date: datetime.date, tzinfo: Tzinfo) -> List[datetime.datetime]:
        return [combine(date, time_of_day, tzinfo) for time_of_day in self.times_of_day]


@dataclass
class WeeklySchedule(kgjson.Base, BaseSchedule):
    times_of_day: List[datetime.time]
    # TODO(2025-11): SUBWAY: parse these into `int`s on deserialization
    days_of_week: List[str]

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        if len(o.times_of_day) == 0:
            raise KgError("times_of_day cannot be empty", o=o)

        if len(o.days_of_week) == 0:
            raise KgError("days_of_week cannot be empty", o=o)

    @override
    def get_interval(self, now: datetime.datetime) -> datetime.date:
        return timehelper.start_of_week(now.date())

    @override
    def get_next_interval(self, now: datetime.datetime) -> datetime.date:
        return self.get_interval(now) + days(7)

    @override
    def get_times(
        self, start_of_week: datetime.date, tzinfo: Tzinfo
    ) -> List[datetime.datetime]:
        days_of_week = sorted(
            humanunits.parse_day_of_week(s) for s in self.days_of_week
        )
        r: List[datetime.datetime] = []
        for day_of_week in days_of_week:
            date = start_of_week + days(day_of_week)
            for time_of_day in self.times_of_day:
                r.append(combine(date, time_of_day, tzinfo))
        return r


@dataclass
class MonthlySchedule(kgjson.Base, BaseSchedule):
    times_of_day: List[datetime.time]
    days_of_month: List[int]

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        if len(o.times_of_day) == 0:
            raise KgError("times_of_day cannot be empty", o=o)

        if len(o.days_of_month) == 0:
            raise KgError("days_of_month cannot be empty", o=o)

    @override
    def get_interval(self, now: datetime.datetime) -> datetime.date:
        return now.date().replace(day=1)

    @override
    def get_next_interval(self, now: datetime.datetime) -> datetime.date:
        return timehelper.next_month(now.date())

    @override
    def get_times(
        self, start_of_month: datetime.date, tzinfo: Tzinfo
    ) -> List[datetime.datetime]:
        max_day = timehelper.days_in_month(start_of_month)
        days_of_month = set(min(x, max_day) for x in self.days_of_month)
        r: List[datetime.datetime] = []
        for day in sorted(days_of_month):
            date = start_of_month.replace(day=day)
            for time_of_day in self.times_of_day:
                r.append(combine(date, time_of_day, tzinfo))
        return r


@dataclass
class Schedule(kgjson.Base):
    hourly: Optional[HourlySchedule] = None
    daily: Optional[DailySchedule] = None
    weekly: Optional[WeeklySchedule] = None
    monthly: Optional[MonthlySchedule] = None

    @override
    @classmethod
    def kgjson_validate(cls, o: Self) -> None:
        # will raise if object is invalid
        o.get_schedule()

    def get_schedule(self) -> BaseSchedule:
        non_null_fields = [
            value
            for value in [
                getattr(self, field.name) for field in dataclasses.fields(self)
            ]
            if value is not None
        ]
        if len(non_null_fields) != 1:
            raise KgError(
                "schedule object must contain exactly one non-null field",
                object=self,
            )

        return non_null_fields[0]

    def get_type(self) -> str:
        if self.hourly is not None:
            return "hourly"
        if self.daily is not None:
            return "daily"
        if self.weekly is not None:
            return "weekly"
        if self.monthly is not None:
            return "monthly"

        impossible()
