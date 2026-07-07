from app.habits import models
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import pgdb


def fetch_habits(db: pgdb.Connection) -> List[models.Habit]:
    T = models.Habit.T
    return db.fetch_all(
        pgdb.SQL("SELECT {} FROM {} WHERE {} IS FALSE").format(
            T.star, T.table, T.deprecated
        ),
        t=pgdb.t(models.Habit),
    )


def fetch_habit_entries(
    db: pgdb.Connection, last_filter: dt.timedelta
) -> List[models.HabitEntry]:
    T = models.HabitEntry.T
    after_date = (timehelper.now() - last_filter).date()
    return db.fetch_all(
        pgdb.SQL("SELECT {} FROM {} WHERE date >= %s").format(T.star, T.table),
        (after_date,),
        t=pgdb.t(models.HabitEntry),
    )


def create_habit_entry(
    db: pgdb.Connection, date: dt.date, habit: str, points: int
) -> None:
    time_created = timehelper.now()
    db.execute(
        """
        INSERT INTO habit_entries(date, habit, original_name, original_points, time_created)
        VALUES (%(date)s, %(habit)s, %(original_name)s, %(original_points)s, %(time_created)s)
        """,
        dict(
            date=date,
            habit=habit,
            original_name=habit,
            original_points=points,
            time_created=time_created,
        ),
    )
