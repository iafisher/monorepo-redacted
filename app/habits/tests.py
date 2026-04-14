from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, pdb
from lib.testing import *

from . import models
from .common import create_habit_entry, fetch_habits, fetch_habit_entries
from .main import cmd


class Test(BaseWithDatabase):
    def test_sql_queries(self):
        with pdb.connect() as db:
            habit_name = "Read"
            db.execute(
                pdb.SQL(
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
                db, date=datetime.date(2025, 7, 26), habit=habit_name, points=1
            )

            entries = fetch_habit_entries(
                db, last_filter=datetime.timedelta(days=365 * 50)
            )
            self.assertEqual(1, len(entries))
            self.assertEqual(habit_name, entries[0].habit)


class TestHelpText(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="habits"),
            """\
Usage: habits SUBCMD

  Manage habits and habit entries.

Subcommands:

  create     . Create a habit.
  entries    . Manage habit entries.
  list       . List habits.
  old        . Manage the old database.
  serve      . Run the webserver.


------------

Usage: habits create ...

  Create a habit.

Arguments:

  -name ARG
  -points ARG
  [-category ARG]       . (default: '')
  [-description ARG]    . (default: '')
  [-once-a-day]


------------

Usage: habits entries SUBCMD

  Manage habit entries.

Subcommands:

  create    . Create a habit entry.
  list      . List habit entries.


------------

Usage: habits entries create ...

  Create a habit entry.

Arguments:

 [-date ARG]     . (default: None)
 [-habit ARG]    . (default: None)


------------

Usage: habits entries list ...

  List habit entries.

Arguments:

 [-last ARG]    . filter to timespan (default: '3d')


------------

Usage: habits list ...

  List habits.


------------

Usage: habits old SUBCMD

  Manage the old database.

Subcommands:

  import    . Import from old database.


------------

Usage: habits old import ...

  Import from old database.

Arguments:

  -entries-csv ARG
  -habits-csv ARG


------------

Usage: habits serve ...

  Run the webserver.

Arguments:

 [-debug]       . Run the server in debug mode.
 [-port ARG]    . (default: 5000)
""",
        )
