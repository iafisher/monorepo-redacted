from app.habits import models
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import pdb


def fetch_habits(db: pdb.Connection) -> List[models.Habit]:
    T = models.Habit.T
    return db.fetch_all(
        pdb.SQL("SELECT {} FROM {} WHERE {} IS FALSE").format(
            T.star, T.table, T.deprecated
        ),
        t=pdb.t(models.Habit),
    )


def fetch_habit_entries(
    db: pdb.Connection, last_filter: datetime.timedelta
) -> List[models.HabitEntry]:
    T = models.HabitEntry.T
    after_date = (timehelper.now() - last_filter).date()
    return db.fetch_all(
        pdb.SQL("SELECT {} FROM {} WHERE date >= %s").format(T.star, T.table),
        (after_date,),
        t=pdb.t(models.HabitEntry),
    )


def create_habit_entry(
    db: pdb.Connection, date: datetime.date, habit: str, points: int
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
