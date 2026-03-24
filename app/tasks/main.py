from typing import Annotated

from iafisher_foundation.prelude import *
from iafisher_foundation import tabular, timehelper
from lib import command, pdb, pushover


KNOWN_CATEGORIES = {"MONO", "FISH", "CITY", "BLOG", "DEEP", "PERS"}
PRIORITY_OR_APPEAL_TO_INT = {"low": 1, "normal": 2, "high": 3}
INT_TO_PRIORITY_OR_APPEAL = {v: k for k, v in PRIORITY_OR_APPEAL_TO_INT.items()}


@dataclass
class Task:
    task_id: str
    title: str
    status: str
    priority: int
    appeal: int
    deadline: Optional[datetime.date]
    blocked_on: Optional[str]
    backlog_until: Optional[datetime.date]
    time_created: datetime.datetime
    time_closed: datetime.datetime


@dataclass
class TaskUpdate:
    task_id: str
    field: str
    old_value: str
    new_value: str
    comment: str
    time_updated: datetime.datetime


def main_create(
    title: str,
    *,
    category: Annotated[
        str, command.Extra(help="options: " + ", ".join(sorted(KNOWN_CATEGORIES)))
    ],
    status: str = "open",
    appeal: str = "normal",
    priority: str = "normal",
    due: Optional[str] = None,
    blocked_on: Optional[str] = None,
    backlog_until: Optional[str] = None,
) -> None:
    if category not in KNOWN_CATEGORIES:
        raise KgError(
            "unknown category", category=category, known_categories=KNOWN_CATEGORIES
        )

    if backlog_until is not None:
        status = "backlog"
        backlog_until_date = datetime.date.fromisoformat(backlog_until)
        if backlog_until_date <= timehelper.today():
            raise KgError(
                "-backlog-until must be a future date", backlog_until=backlog_until_date
            )

    if due is not None:
        due_date = datetime.date.fromisoformat(due)
        if due_date <= timehelper.today():
            raise KgError("-due must be a future date", due=due_date)

    priority_appeal_choices = list(PRIORITY_OR_APPEAL_TO_INT.keys())
    priority_int = PRIORITY_OR_APPEAL_TO_INT.get(priority)
    if priority_int is None:
        raise KgError(
            "unknown priority", priority=priority, choices=priority_appeal_choices
        )
    appeal_int = PRIORITY_OR_APPEAL_TO_INT.get(appeal)
    if appeal_int is None:
        raise KgError("unknown appeal", appeal=appeal, choices=priority_appeal_choices)

    with pdb.connect() as db:
        time_created = timehelper.now()
        new_task_id = db.fetch_val(
            """
            INSERT INTO tasks(
                task_id,
                title,
                status,
                priority,
                appeal,
                deadline,
                blocked_on,
                backlog_until,
                time_created
            )
            VALUES(
                %(category)s || '-' || to_char(nextval('task_id_' || %(category_lower)s), 'FM00000'),
                %(title)s,
                %(status)s,
                %(priority)s,
                %(appeal)s,
                %(due)s,
                %(blocked_on)s,
                %(backlog_until)s,
                %(time_created)s
            )
            RETURNING task_id
            """,
            dict(
                category=category,
                category_lower=category.lower(),
                title=title,
                status=status,
                priority=priority_int,
                appeal=appeal_int,
                due=due,
                blocked_on=blocked_on,
                backlog_until=backlog_until,
                time_created=time_created,
            ),
        )
        print(f"Created {new_task_id}.")


def main_list(*, backlog: bool = False) -> None:
    with pdb.connect() as db:
        # TODO(2026-03): More elegant way of doing this?
        if backlog:
            status1 = status2 = "backlog"
        else:
            status1 = "open"
            status2 = "blocked"

        tasks = db.fetch_all(
            """
            SELECT *
            FROM tasks
            WHERE status = %(status1)s OR status = %(status2)s
            ORDER BY deadline ASC, priority DESC, appeal DESC, time_created ASC
            """,
            dict(status1=status1, status2=status2),
            t=pdb.t(Task),
        )

    _print_list(tasks)


def main_mark_backlog(task_id: str, *, until: Optional[str]) -> None:
    with pdb.connect() as db:
        db.execute(
            "CALL tasks_mark_backlog(%(task_id)s, %(until)s)",
            dict(task_id=task_id, until=until),
        )


def main_mark_blocked(
    task_id: str, *, blocked_on: Annotated[str, command.Extra(name="-on")]
) -> None:
    with pdb.connect() as db:
        db.execute(
            "CALL tasks_mark_blocked(%(task_id)s, %(blocked_on)s)",
            dict(task_id=task_id, blocked_on=blocked_on),
        )


def main_mark_done(task_id: str) -> None:
    with pdb.connect() as db:
        db.execute("CALL tasks_mark_done(%(task_id)s)", dict(task_id=task_id))


def main_mark_open(task_id: str) -> None:
    with pdb.connect() as db:
        db.execute("CALL tasks_mark_open(%(task_id)s)", dict(task_id=task_id))


def main_mark_wontfix(task_id: str) -> None:
    with pdb.connect() as db:
        db.execute("CALL tasks_mark_wontfix(%(task_id)s)", dict(task_id=task_id))


def _print_list(tasks: List[Task]) -> None:
    table = tabular.Table()
    table.header(["id", "title", "status", "deadline", "priority", "appeal", "created"])
    for task in tasks:
        if task.status == "blocked":
            status = f"blocked on {task.blocked_on}"
        elif task.status == "backlog" and task.backlog_until is not None:
            status = f"backlog until {task.backlog_until}"
        else:
            status = task.status

        table.row(
            [
                task.task_id,
                task.title,
                status,
                task.deadline or "",
                INT_TO_PRIORITY_OR_APPEAL[task.priority],
                INT_TO_PRIORITY_OR_APPEAL[task.appeal],
                task.time_created,
            ]
        )
    table.flush()


def main_update(
    task_id: str,
    *,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    appeal: Optional[str] = None,
    deadline: Optional[str] = None,
    backlog_until: Optional[str] = None,
) -> None:
    field_name_to_new_value = {
        "title": title,
        "priority": (
            PRIORITY_OR_APPEAL_TO_INT[priority] if priority is not None else None
        ),
        "appeal": PRIORITY_OR_APPEAL_TO_INT[appeal] if appeal is not None else None,
        "deadline": deadline,
        "backlog_until": backlog_until,
    }

    with pdb.connect() as db:
        for field_name, new_value in field_name_to_new_value.items():
            if new_value is None:
                continue

            db.execute(
                f"""
                UPDATE tasks SET {field_name} = %(new_value)s WHERE task_id = %(task_id)s
                """,
                dict(task_id=task_id, new_value=new_value),
            )


def main_jobs_reopen_if_backlog_until_past() -> None:
    today = timehelper.today()
    with pdb.connect() as db:
        # TODO(2026-03): Would be nicer to use the stored procedure.
        task_ids_to_revisit = db.fetch_all(
            """
            UPDATE tasks
            SET status = 'open', backlog_until = NULL
            WHERE backlog_until <= %(today)s
            RETURNING task_id
            """,
            dict(today=today),
            t=pdb.tuple_row,
        )

        n = len(task_ids_to_revisit)
        if n > 0:
            LOG.info("revisited %d task(s): %r", n, task_ids_to_revisit)


def main_jobs_notify_if_due_soon() -> None:
    tomorrow = timehelper.today() + datetime.timedelta(days=1)
    with pdb.connect() as db:
        tasks_due_soon = db.fetch_all(
            """
            SELECT *
            FROM tasks
            WHERE deadline IS NOT NULL AND deadline <= %(tomorrow)s
            """,
            dict(tomorrow=tomorrow),
            t=pdb.t(Task),
        )

    for task in tasks_due_soon:
        pushover.notify(f"Task due soon: {task.title}")


cmd = command.Group()

jobs_cmd = command.Group()
jobs_cmd.add2(
    "reopen-if-backlog-until-past",
    main_jobs_reopen_if_backlog_until_past,
    less_logging=False,
)
jobs_cmd.add2(
    "notify-if-due-soon",
    main_jobs_notify_if_due_soon,
    help="Commands to run as scheduled jobs.",
    less_logging=False,
)

mark_cmd = command.Group(help="Mark the status of tasks.")
mark_cmd.add2("backlog", main_mark_backlog)
mark_cmd.add2("blocked", main_mark_blocked)
mark_cmd.add2("done", main_mark_done)
mark_cmd.add2("open", main_mark_open)
mark_cmd.add2("wontfix", main_mark_wontfix)

cmd.add2("create", main_create, help="Create a new task.")
cmd.add("jobs", jobs_cmd)
cmd.add2("list", main_list, help="List tasks.")
cmd.add("mark", mark_cmd)
cmd.add2("update", main_update, help="Update an existing task.")


if __name__ == "__main__":
    command.dispatch(cmd)
