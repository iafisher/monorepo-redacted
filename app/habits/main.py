import csv
from typing import Annotated

from app.habits import models
from app.habits.common import (
    create_habit_entry,
    fetch_habit_entries,
    fetch_habits,
)
from app.habits.webserver import cmd as webserver_cmd
from iafisher_foundation import tabular, timehelper
from iafisher_foundation.prelude import *
from lib import command, fzf, humanunits, pdb


def main_create(
    *,
    name: str,
    points: int,
    once_a_day: bool,
    category: str = "",
    description: str = "",
) -> None:
    with pdb.connect() as db:
        T = models.Habit.T
        time_created = timehelper.now()
        db.execute(
            pdb.SQL(
                """
                INSERT INTO {table}({name}, {points}, {category}, {once_a_day}, {description}, {time_created})
                VALUES (%(name)s, %(points)s, %(category)s, %(once_a_day)s, %(description)s, %(time_created)s)
                """
            ).format(
                table=T.table,
                name=T.name,
                points=T.points,
                category=T.category,
                once_a_day=T.once_a_day,
                description=T.description,
                time_created=T.time_created,
            ),
            dict(
                name=name,
                points=points,
                category=category,
                once_a_day=once_a_day,
                description=description,
                time_created=time_created,
            ),
        )


def main_entries_create(
    *,
    habit_name: Annotated[Optional[str], command.Extra(name="-habit")] = None,
    date: Annotated[
        Optional[datetime.date], command.Extra(converter=datetime.date.fromisoformat)
    ] = None,
) -> None:
    if date is None:
        today = datetime.date.today()
        date_options = get_date_options(today)
        date = fzf.select_map(date_options)

    with pdb.connect() as db:
        if habit_name is not None:
            habit = fetch_habit_by_name(db, habit_name)
        else:
            habit_options = fetch_habits(db)
            habit = fzf.select_key(habit_options, key=lambda habit: habit.name)

        create_habit_entry(db, date, habit.name, habit.points)

    print("Created {habit.name!r} entry for {date}.")


def get_date_options(today: datetime.date) -> List[Tuple[str, datetime.date]]:
    r: List[Tuple[str, datetime.date]] = []
    r.append(("today", today))
    r.append(("yesterday", (today - datetime.timedelta(days=1))))
    for days in range(2, 8):
        date = today - datetime.timedelta(days=days)
        r.append((date.isoformat(), date))
    return r


def fetch_habit_by_name(db: pdb.Connection, name: str) -> models.Habit:
    sql_star = models.Habit.T.star
    table_name = models.Habit.T.table
    return db.fetch_one(
        pdb.SQL("SELECT {} FROM {} WHERE name = %s").format(sql_star, table_name),
        (name,),
        t=pdb.t(models.Habit),
    )


def main_entries_list(
    *,
    last_filter: Annotated[
        datetime.timedelta,
        command.Extra(
            name="-last",
            help="filter to timespan",
            default="3d",
            converter=humanunits.parse_duration,
        ),
    ],
) -> None:
    with pdb.connect() as db:
        habit_entry_models = fetch_habit_entries(db, last_filter)

    habit_entry_models.sort(key=lambda entry: entry.date)

    last_date = None
    for habit_entry_model in habit_entry_models:
        if last_date is not None and habit_entry_model.date != last_date:
            print()

        print(f"{habit_entry_model.date}  {habit_entry_model.habit}")
        last_date = habit_entry_model.date


def main_list() -> None:
    with pdb.connect() as db:
        habits = fetch_habits(db)

    table = tabular.Table()
    table.header(["name", "category", "points", "once a day"])
    for habit in sorted(habits, key=lambda habit: habit.name):
        table.row([habit.name, habit.category, habit.points, habit.once_a_day])
    table.flush()


def main_old_import(*, habits_csv: str, entries_csv: str) -> None:
    with pdb.connect() as db:
        # Export with:
        #
        #   .mode csv
        #   .headers on
        #   .output /tmp/habits.csv
        #   select name, points, category, once_a_day, deprecated, description, created_at from habits;
        #
        with open(habits_csv, newline="") as f:
            reader = csv.DictReader(f)
            rows_to_insert: List[Dict[str, Any]] = []
            for row in reader:
                rows_to_insert.append(
                    dict(
                        name=row["name"],
                        points=row["points"],
                        category=row["category"],
                        once_a_day=row["once_a_day"] == "1",
                        deprecated=row["deprecated"] == "1",
                        description=row["description"],
                        time_created=timehelper.from_epoch_secs_utc(
                            float(row["created_at"])
                        ),
                    )
                )

            db.execute_many(
                """
                INSERT INTO habits(
                    name,
                    points,
                    category,
                    once_a_day,
                    deprecated,
                    description,
                    time_created
                ) VALUES(
                    %(name)s,
                    %(points)s,
                    %(category)s,
                    %(once_a_day)s,
                    %(deprecated)s,
                    %(description)s,
                    %(time_created)s
                );
                """,
                rows_to_insert,
            )

        # Export with:
        #
        #   .mode csv
        #   .headers on
        #   .output /tmp/entries.csv
        #   select date, habits.name AS habit, t.name AS original_name, t.points AS original_points, t.created_at from habit_entries t left join habits on habits.id = t.habit;
        #
        with open(entries_csv, newline="") as f:
            reader = csv.DictReader(f)
            rows_to_insert = []
            for row in reader:
                rows_to_insert.append(
                    dict(
                        date=datetime.date.fromisoformat(row["date"]),
                        habit=row["habit"],
                        original_name=row["original_name"],
                        original_points=row["original_points"],
                        time_created=timehelper.from_epoch_secs_utc(
                            float(row["created_at"])
                        ),
                    )
                )

            db.execute_many(
                """
                INSERT INTO habit_entries(
                    date,
                    habit,
                    original_name,
                    original_points,
                    time_created
                ) VALUES(
                    %(date)s,
                    %(habit)s,
                    %(original_name)s,
                    %(original_points)s,
                    %(time_created)s
                );
                """,
                rows_to_insert,
            )


cmd = command.Group(help="Manage habits and habit entries.")

cmd.add2("create", main_create, help="Create a habit.")

entries_cmd = command.Group(help="Manage habit entries.")
entries_cmd.add2("create", main_entries_create, help="Create a habit entry.")
entries_cmd.add2("list", main_entries_list, help="List habit entries.")
cmd.add("entries", entries_cmd)

cmd.add2("list", main_list, help="List habits.")

old_cmd = command.Group(help="Manage the old database.")
old_cmd.add2("import", main_old_import, help="Import from old database.")
cmd.add("old", old_cmd)

cmd.add("serve", webserver_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
