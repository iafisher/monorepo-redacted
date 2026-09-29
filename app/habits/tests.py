from iafisher import timehelper
from iafisher.prelude import *
from lib import command, pgdb
from lib.testing import *

from . import models
from .common import create_habit_entry, fetch_habits, fetch_habit_entries
from .main import cmd


class Test(BaseWithDatabase):
    def test_sql_queries(self):
        with pgdb.connect() as db:
            habit_name = "Read"
            db.execute(
                pgdb.SQL(
                    "INSERT INTO {}({}, {}, {}, {}) VALUES(%(name)s, %(points)s, %(category)s, %(time_created)s)"
                ).format(
                    models.Habit.T.table,
                    models.Habit.T.name,
                    models.Habit.T.points,
                    models.Habit.T.category,
                    models.Habit.T.time_created,
                ),
                dict(
                    name=habit_name,
                    points=1,
                    category="Productivity",
                    time_created=timehelper.epoch(),
                ),
            )

            habits = fetch_habits(db)
            self.assertEqual(1, len(habits))
            self.assertEqual(habit_name, habits[0].name)

            create_habit_entry(
                db, date=dt.date(2025, 7, 26), habit=habit_name, points=1
            )

            entries = fetch_habit_entries(db, last_filter=dt.timedelta(days=365 * 50))
            self.assertEqual(1, len(entries))
            self.assertEqual(habit_name, entries[0].habit)


class TestHelpText(Base):
    def test_help_text(self):
        self.assertTrue(len(command.get_help_text_recursive(cmd, program="habits")) > 0)
