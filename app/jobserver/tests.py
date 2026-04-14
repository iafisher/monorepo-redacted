import json
import requests
import subprocess
import tempfile
import time
import unittest
import warnings
from pathlib import Path

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import kgenv, localdb
from lib.testing import *

from expecttest import TestCase

from .server import Job, State
from .scheduler import (
    BaseSchedule,
    DailySchedule,
    HourlySchedule,
    MonthlySchedule,
    Schedule,
    WeeklySchedule,
    mins,
)

MINS_IN_DAY = 60 * 24
# TODO(2025-11): Standard for test vs. prod ports
TEST_PORT = 10500


def add_real_clock_time(
    dt: datetime.datetime, delta: datetime.timedelta
) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt + delta
    dt_utc = dt.astimezone(datetime.timezone.utc)
    return (dt_utc + delta).astimezone(dt.tzinfo)


class Test(Base, TestCase):
    def test_scheduler_deserialization(self):
        with self.assertRaises(KgError):
            Schedule.deserialize(dict())

        with self.assertRaises(KgError):
            Schedule.deserialize(
                dict(hourly=dict(interval_mins=60), daily=dict(times_of_day=["11am"]))
            )

        with self.assertRaises(KgError):
            Schedule.deserialize(dict(daily=dict(times_of_day=[])))

        schedule = Schedule.deserialize(dict(daily=dict(times_of_day=["11am"])))
        self.assertEqual(
            DailySchedule(times_of_day=[datetime.time(11, 0)]), schedule.get_schedule()
        )

    def test_scheduler_calculate_next_run_time(self):
        def timetable(
            schedule: BaseSchedule,
            n: int = 5,
            wakeup_interval_mins: int = 1,
            start_datetime: datetime.datetime = datetime.datetime(
                2025, 11, 22, hour=0, minute=0
            ),
        ) -> str:
            now = start_datetime
            builder: List[str] = []
            for _ in range(n):
                next_scheduled_time = schedule.get_next_scheduled_time(now)
                weekday = now.strftime("%a")
                if next_scheduled_time < now:
                    builder.append(
                        f"{weekday} {now}: next at {next_scheduled_time} (INVALID)"
                    )
                else:
                    builder.append(f"{weekday} {now}: next at {next_scheduled_time}")
                now = max(
                    add_real_clock_time(next_scheduled_time, mins(1)),
                    add_real_clock_time(now, mins(wakeup_interval_mins)),
                )
            return "\n".join(builder)

        schedule = HourlySchedule(
            interval_mins=60,
            start_time_of_day=datetime.time(4, 0),
            end_time_of_day=datetime.time(10, 0),
        )
        self.maxDiff = None
        self.assertExpectedInline(
            timetable(schedule, n=8),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-22 04:00:00
Sat 2025-11-22 04:01:00: next at 2025-11-22 05:00:00
Sat 2025-11-22 05:01:00: next at 2025-11-22 06:00:00
Sat 2025-11-22 06:01:00: next at 2025-11-22 07:00:00
Sat 2025-11-22 07:01:00: next at 2025-11-22 08:00:00
Sat 2025-11-22 08:01:00: next at 2025-11-22 09:00:00
Sat 2025-11-22 09:01:00: next at 2025-11-22 10:00:00
Sat 2025-11-22 10:01:00: next at 2025-11-23 04:00:00""",
        )

        schedule = HourlySchedule(interval_mins=5)
        self.assertExpectedInline(
            timetable(schedule, wakeup_interval_mins=7),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-22 00:05:00
Sat 2025-11-22 00:07:00: next at 2025-11-22 00:10:00
Sat 2025-11-22 00:14:00: next at 2025-11-22 00:15:00
Sat 2025-11-22 00:21:00: next at 2025-11-22 00:25:00
Sat 2025-11-22 00:28:00: next at 2025-11-22 00:30:00""",
        )

        schedule = HourlySchedule(interval_mins=12 * 60)
        self.assertExpectedInline(
            timetable(schedule, wakeup_interval_mins=7, n=16),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-22 12:00:00
Sat 2025-11-22 12:01:00: next at 2025-11-23 00:00:00
Sun 2025-11-23 00:01:00: next at 2025-11-23 12:00:00
Sun 2025-11-23 12:01:00: next at 2025-11-24 00:00:00
Mon 2025-11-24 00:01:00: next at 2025-11-24 12:00:00
Mon 2025-11-24 12:01:00: next at 2025-11-25 00:00:00
Tue 2025-11-25 00:01:00: next at 2025-11-25 12:00:00
Tue 2025-11-25 12:01:00: next at 2025-11-26 00:00:00
Wed 2025-11-26 00:01:00: next at 2025-11-26 12:00:00
Wed 2025-11-26 12:01:00: next at 2025-11-27 00:00:00
Thu 2025-11-27 00:01:00: next at 2025-11-27 12:00:00
Thu 2025-11-27 12:01:00: next at 2025-11-28 00:00:00
Fri 2025-11-28 00:01:00: next at 2025-11-28 12:00:00
Fri 2025-11-28 12:01:00: next at 2025-11-29 00:00:00
Sat 2025-11-29 00:01:00: next at 2025-11-29 12:00:00
Sat 2025-11-29 12:01:00: next at 2025-11-30 00:00:00""",
        )

        schedule = HourlySchedule(
            interval_mins=30,
            start_time_of_day=datetime.time(9, 0),
            end_time_of_day=datetime.time(9, 30),
            days_of_week=["mon", "wed"],
        )
        self.assertExpectedInline(
            timetable(schedule, wakeup_interval_mins=7, n=7),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-24 09:00:00
Mon 2025-11-24 09:01:00: next at 2025-11-24 09:30:00
Mon 2025-11-24 09:31:00: next at 2025-11-26 09:00:00
Wed 2025-11-26 09:01:00: next at 2025-11-26 09:30:00
Wed 2025-11-26 09:31:00: next at 2025-12-01 09:00:00
Mon 2025-12-01 09:01:00: next at 2025-12-01 09:30:00
Mon 2025-12-01 09:31:00: next at 2025-12-03 09:00:00""",
        )

        schedule = DailySchedule(
            times_of_day=[datetime.time(4, 0), datetime.time(13, 30)]
        )
        self.assertExpectedInline(
            timetable(schedule),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-22 04:00:00
Sat 2025-11-22 04:01:00: next at 2025-11-22 13:30:00
Sat 2025-11-22 13:31:00: next at 2025-11-23 04:00:00
Sun 2025-11-23 04:01:00: next at 2025-11-23 13:30:00
Sun 2025-11-23 13:31:00: next at 2025-11-24 04:00:00""",
        )

        schedule = WeeklySchedule(
            times_of_day=[datetime.time(22, 0)], days_of_week=["THURSDAY", "monday"]
        )
        # 2025-11-22 is a Saturday, so next jobs should run on 2025-11-24 (Monday)
        # and 2025-11-27 (Thursday).
        self.assertExpectedInline(
            timetable(schedule),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-24 22:00:00
Mon 2025-11-24 22:01:00: next at 2025-11-27 22:00:00
Thu 2025-11-27 22:01:00: next at 2025-12-01 22:00:00
Mon 2025-12-01 22:01:00: next at 2025-12-04 22:00:00
Thu 2025-12-04 22:01:00: next at 2025-12-08 22:00:00""",
        )

        schedule = MonthlySchedule(
            times_of_day=[datetime.time(1, 0)], days_of_month=[1, 31]
        )
        self.assertExpectedInline(
            timetable(schedule),
            """\
Sat 2025-11-22 00:00:00: next at 2025-11-30 01:00:00
Sun 2025-11-30 01:01:00: next at 2025-12-01 01:00:00
Mon 2025-12-01 01:01:00: next at 2025-12-31 01:00:00
Wed 2025-12-31 01:01:00: next at 2026-01-01 01:00:00
Thu 2026-01-01 01:01:00: next at 2026-01-31 01:00:00""",
        )

        # Q: What happens in February if the job runs on the 29th, 30th, and 31st of the month?
        # A: The job runs once at the end of February, on the 28th.
        schedule = MonthlySchedule(
            times_of_day=[datetime.time(1, 0)], days_of_month=[29, 30, 31]
        )
        self.assertExpectedInline(
            timetable(
                schedule,
                start_datetime=datetime.datetime(2025, 2, 28, hour=0, minute=0),
            ),
            """\
Fri 2025-02-28 00:00:00: next at 2025-02-28 01:00:00
Fri 2025-02-28 01:01:00: next at 2025-03-29 01:00:00
Sat 2025-03-29 01:01:00: next at 2025-03-30 01:00:00
Sun 2025-03-30 01:01:00: next at 2025-03-31 01:00:00
Mon 2025-03-31 01:01:00: next at 2025-04-29 01:00:00""",
        )

        # DST: falling back
        schedule = DailySchedule(
            times_of_day=[datetime.time(1, 30), datetime.time(1, 45)]
        )
        self.assertExpectedInline(
            timetable(
                schedule,
                n=4,
                start_datetime=datetime.datetime(
                    2025, 11, 2, hour=0, minute=0, tzinfo=timehelper.TZ_NYC
                ),
            ),
            """\
Sun 2025-11-02 00:00:00-04:00: next at 2025-11-02 01:30:00-04:00
Sun 2025-11-02 01:31:00-04:00: next at 2025-11-02 01:45:00-04:00
Sun 2025-11-02 01:46:00-04:00: next at 2025-11-03 01:30:00-05:00
Mon 2025-11-03 01:31:00-05:00: next at 2025-11-03 01:45:00-05:00""",
        )

        # DST: springing forward
        schedule = DailySchedule(times_of_day=[datetime.time(2, 30)])
        self.assertExpectedInline(
            timetable(
                schedule,
                n=3,
                start_datetime=datetime.datetime(
                    2025, 3, 9, hour=0, minute=0, tzinfo=timehelper.TZ_NYC
                ),
            ),
            """\
Sun 2025-03-09 00:00:00-05:00: next at 2025-03-09 02:30:00-05:00
Sun 2025-03-09 03:31:00-04:00: next at 2025-03-10 02:30:00-04:00
Mon 2025-03-10 02:31:00-04:00: next at 2025-03-11 02:30:00-04:00""",
        )

    def test_server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["KG_TEST_DIR"] = tmpdir
            tmpdirp = Path(tmpdir)
            os.mkdir(tmpdirp / "apps")
            appdir = tmpdirp / "apps" / "jobserver"
            os.mkdir(appdir)
            os.mkdir(tmpdirp / "apps" / "testjob")

            with localdb.connect() as db:
                # TODO(2025-12): common test utility
                schema_path = kgenv.get_code_dir() / "migrations" / "initial-sqlite.sql"
                db.executescript(schema_path.read_text())

            job1 = Job(
                name="testjob",
                cmd=["echo", "hello"],
                schedule=Schedule(hourly=HourlySchedule(interval_mins=1)),
                date_added=datetime.date(2025, 1, 1),
                enabled=True,
                run_now=True,
                machines=["laptop"],
            )
            job1_config_path = tmpdirp / "apps" / "testjob" / "jobserver.json"
            job1_config_path.write_text(State(jobs=[job1]).serialize())
            job2 = Job(
                name="testjob2",
                cmd=["echo", "[[date]]"],
                schedule=Schedule(hourly=HourlySchedule(interval_mins=1)),
                date_added=datetime.date(2025, 1, 1),
                enabled=True,
                run_now=True,
            )

            state_file = appdir / "state.json"
            state = State(jobs=[job1, job2])
            state_file.write_text(state.serialize())

            # TODO(2025-02): absolute path
            py_exe = ".venv/bin/python3"
            kg_exe = "app/kg/main.py"
            proc = None
            try:
                proc = subprocess.Popen(
                    [
                        py_exe,
                        kg_exe,
                        "jobs",
                        "daemon",
                        "start",
                        "-wakeup-interval",
                        "10ms",
                        "-port",
                        str(TEST_PORT),
                    ]
                )
                print("Started process", proc.pid)
                wait_for_pid_lockfile(appdir)
                self.assertTrue((appdir / "state.lock").exists())
                time.sleep(0.5)

                response = requests.post(
                    f"http://localhost:{TEST_PORT}",
                    json=dict(method="jobserver.list_jobs", data={}),
                ).json()
                self.assertEqual(2, len(response["jobs"]))
            finally:
                if proc is not None:
                    proc.terminate()
                    proc.wait()
                    print("Killed process", proc.pid)

            self.assertFalse((appdir / "pid.lock").exists())
            self.assertTrue(state_file.exists())

            testjob_paths = list(
                p
                for p in (tmpdirp / "logs" / "testjob").iterdir()
                if p.suffix == ".log"
            )
            # TODO(2025-12): This assertion is flaky.
            self.assertEqual(1, len(testjob_paths))
            stdout_path = testjob_paths[0]
            self.assertEqual("hello\n", stdout_path.read_text())

            # `[[date]]` pattern should have been substituted by jobserver
            testjob2_paths = list(
                p
                for p in (tmpdirp / "logs" / "testjob2").iterdir()
                if p.suffix == ".log"
            )
            assert len(testjob2_paths) == 1
            self.assertEqual(1, len(testjob2_paths))
            stdout_path2 = testjob2_paths[0]
            self.assertRegex(stdout_path2.as_posix(), r".*\.log")
            self.assertRegex(
                stdout_path2.read_text(),
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}\n$",
            )

            os.environ["NO_COLOR"] = "1"
            stdout = shell(py_exe, kg_exe, "jobs", "list", "-verbose")
            self.assertExpectedInline(
                expunge_numbers(expunge_datetimes(stdout)),
                """\
testjob
- Command: ['echo', 'hello']
- Last run: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- Exit status: 0
- Time: XXX wall, XXX user, XXX sys
- Memory: XXX byte(s)
- Next run: XXXXXXXXXXXXXXXXXXXXXXXXX
- Enabled: true

testjob2
- Command: ['echo', '[[date]]']
- Last run: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- Exit status: 0
- Time: XXX wall, XXX user, XXX sys
- Memory: XXX byte(s)
- Next run: XXXXXXXXXXXXXXXXXXXXXXXXX
- Enabled: true
""",
            )

            # Test that updating a job's config does not reset its last run info.
            shell(py_exe, kg_exe, "jobs", "schedule", job1_config_path, "-replace")
            time.sleep(0.5)

            stdout = shell(py_exe, kg_exe, "jobs", "list", "-verbose")
            # TODO(2025-11): Sometimes fails flakily when "Next run" is "now".
            self.assertExpectedInline(
                expunge_numbers(expunge_datetimes(stdout)),
                """\
testjob
- Command: ['echo', 'hello']
- Last run: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- Exit status: 0
- Time: XXX wall, XXX user, XXX sys
- Memory: XXX byte(s)
- Next run: XXXXXXXXXXXXXXXXXXXXXXXXX
- Enabled: true

testjob2
- Command: ['echo', '[[date]]']
- Last run: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- Exit status: 0
- Time: XXX wall, XXX user, XXX sys
- Memory: XXX byte(s)
- Next run: XXXXXXXXXXXXXXXXXXXXXXXXX
- Enabled: true
""",
            )

            stdout = shell(py_exe, kg_exe, "jobs", "history", "testjob")
            self.assertExpectedInline(
                expunge_numbers(expunge_datetimes(stdout)),
                """\
time run                          exit status  wall time
XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX  0            XXX
""",
            )

    @unittest.skip("manual test")
    def test_sighup_bug(self):
        warnings.simplefilter("ignore", ResourceWarning)
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["KG_TEST_DIR"] = tmpdir
            tmpdirp = Path(tmpdir)
            os.mkdir(tmpdirp / "apps")
            appdir = tmpdirp / "apps" / "jobserver"
            os.mkdir(appdir)
            os.mkdir(tmpdirp / "apps" / "testjob")

            job = Job(
                name="testjob",
                cmd=["echo", "hello"],
                schedule=Schedule(hourly=HourlySchedule(interval_mins=1)),
                date_added=datetime.date(2025, 1, 1),
                enabled=True,
                run_now=True,
                machines=["laptop"],
            )
            job_config_path = tmpdirp / "apps" / "testjob" / "jobserver.json"
            job_config_path.write_text(State(jobs=[job]).serialize())

            state_file = appdir / "state.json"
            state = State(jobs=[job])

            # TODO(2025-02): absolute path
            py_exe = ".venv/bin/python3"
            kg_exe = "app/kg/main.py"
            lockfile = appdir / "pid.lock"
            start_time = time.time()
            deadlocks = 0
            while True:
                if time.time() - start_time > 60 * 30:
                    print(f"exiting loop after 30 minutes; deadlocks: {deadlocks}")
                    break

                state_file.write_text(state.serialize())
                proc = None
                try:
                    proc = subprocess.Popen(
                        [
                            py_exe,
                            kg_exe,
                            "jobs",
                            "daemon",
                            "start",
                            "-wakeup-interval",
                            "1ms",
                            "-port",
                            str(TEST_PORT),
                        ]
                    )
                    print("Started process", proc.pid)
                    wait_for_pid_lockfile(appdir)

                    shell(py_exe, kg_exe, "jobs", "daemon", "kill")
                    try:
                        proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        end_time = time.time()
                        print(
                            "hit deadlock after {:.1f} seconds".format(
                                end_time - start_time
                            )
                        )
                        start_time = end_time
                        proc.kill()
                        lockfile.unlink(missing_ok=True)
                        deadlocks += 1
                    else:
                        self.assertFalse(lockfile.exists())
                finally:
                    if proc is not None:
                        proc.terminate()
                        proc.wait()
                        print("Killed process", proc.pid)

    def test_state_file_backwards_compatibility(self):
        json_d = json.loads(SAMPLE_STATE)
        State.deserialize(json_d)


# matches either a multi-digit integer, or a decimal number, optionally followed by 's'
# (multi-digit so it doesn't match, e.g., 'exit code: 0' which is OK)
_numbers_pattern = lazy_re(r"\b([0-9]{2,}|[0-9]+\.[0-9]+)s?\b")


def expunge_numbers(s: str) -> str:
    return _numbers_pattern.get().sub("XXX", s)


def wait_for_pid_lockfile(appdir: pathlib.Path) -> None:
    p = appdir / "pid.lock"
    start = time.time()
    while True:
        if p.exists():
            return
        if time.time() - start > 5.0:
            raise Exception("timed out waiting for pid lockfile")
        time.sleep(0.1)


SAMPLE_STATE = """\
{
    "jobs": [
        {
            "name": "testjob",
            "cmd": [
                "date"
            ],
            "appdir": "test",
            "interval_mins": 1440,
            "date_added": "2025-01-31",
            "enabled": false,
            "run_now": false,
            "extra_path": null,
            "extra_pythonpath": null,
            "start_time_of_day": "13:00:00",
            "last_run_time": "2025-02-06T18:05:34.378124-05:00",
            "last_exit_status": 0,
            "last_stats": null
        },
        {
            "name": "testfail",
            "cmd": [
                "this_command_does_not_exist"
            ],
            "appdir": "test",
            "interval_mins": 1440,
            "date_added": "2025-02-06",
            "enabled": false,
            "run_now": false,
            "extra_path": null,
            "extra_pythonpath": null,
            "start_time_of_day": "23:59:00",
            "last_run_time": "2025-02-06T17:52:26.268873-05:00",
            "last_exit_status": 65280,
            "last_stats": null
        },
        {
            "name": "statcollect",
            "cmd": [
                "/Users/iafisher/.ian/repos/current/bin/statcollect",
                "-exclude",
                "obsidian_journal_count",
                "-yesterday",
                "-output",
                "append"
            ],
            "appdir": "statcollect",
            "interval_mins": 1440,
            "date_added": "2025-02-19",
            "enabled": true,
            "run_now": false,
            "extra_path": null,
            "extra_pythonpath": null,
            "start_time_of_day": "04:00:00",
            "last_run_time": "2025-06-15T04:07:20.079124-04:00",
            "last_exit_status": 0,
            "last_stats": {
                "wall_time_secs": 3.0908737182617188,
                "user_time_secs": 0.25590599999999997,
                "system_time_secs": 0.21892499999999998,
                "max_memory": 106987520
            }
        }
    ]
}
"""
