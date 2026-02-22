import json
import signal
import subprocess
import time
from typing import Annotated

from iafisher_foundation import colors, tabular, timehelper
from iafisher_foundation.prelude import *
from lib import command, fzf, humanunits, iterhelper, kgenv, localdb, oshelper

from . import models, rpc, server
from .scheduler import Schedule

# TODO(2025-01): `kg jobs history` command


def main_daemon_kill(
    *,
    sigkill: Annotated[
        bool, command.Extra(help="Send SIGKILL instead of SIGHUP.")
    ] = False,
) -> None:
    pid = read_daemon_pid()
    if pid is not None and oshelper.is_pid_running(pid):
        # rely on launchd/systemd to auto-restart
        sig = signal.SIGKILL if sigkill else signal.SIGHUP
        os.kill(pid, sig)
    else:
        print("daemon is not running")
        sys.exit(1)


def main_daemon_start(
    *,
    wakeup_interval: Annotated[
        datetime.timedelta,
        command.Extra(
            converter=humanunits.parse_duration,
            default="1s",
            help="wake up this often to check for jobs to run",
        ),
    ],
    log_interval: Annotated[
        datetime.timedelta,
        command.Extra(
            converter=humanunits.parse_duration,
            default="5m",
            help="write a heartbeat log message this often",
        ),
    ],
    port: int = rpc.PORT,
) -> None:
    server.run_loop(
        wakeup_interval=wakeup_interval,
        log_interval=log_interval,
        rpc_port=port,
    )


def main_daemon_status() -> None:
    pid = read_daemon_pid()
    if pid is not None and oshelper.is_pid_running(pid):
        print(f"daemon is running (pid: {pid})")
        sys.exit(0)
    else:
        print("daemon is not running")
        sys.exit(1)


def read_daemon_pid() -> Optional[int]:
    try:
        return int(server.pid_lock_file_path().read_text())
    except (FileNotFoundError, OSError, ValueError):
        return None


def main_daemon_test_crash() -> None:
    pid = read_daemon_pid()
    if pid is not None and oshelper.is_pid_running(pid):
        os.kill(pid, signal.SIGUSR1)
    else:
        print("daemon is not running")
        sys.exit(1)


def main_disable(name: Optional[str]) -> None:
    enable_disable(name, False, "job is already disabled")


def main_enable(name: Optional[str]) -> None:
    enable_disable(name, True, "job is already enabled")


def enable_disable(name: Optional[str], new_value: bool, error: str) -> None:
    if name is None:
        name = fzf_job_name(is_enabled=not new_value)

    with oshelper.LockFile(server.state_lock_file_path(), exclusive=True):
        state = server.load_state_holding_lock()
        job = server.must_find_job_in_state(state, name)
        if job.enabled == new_value:
            raise KgError(error, name=name)
        job.enabled = new_value
        server.save_state_holding_lock(state)


def main_history(
    name: str,
    *,
    limit: Annotated[int, command.Extra(help="pass -1 to show all previous runs")] = 5,
) -> None:

    with localdb.connect() as db:
        entries = fetch_job_history(db, name, limit=(None if limit == -1 else limit))

    table = tabular.Table()
    table.header(["time run", "exit status", "wall time"])
    for time_run_epoch_secs, exit_status, wall_time_secs in entries:
        time_run = timehelper.from_epoch_secs(time_run_epoch_secs)
        table.row([time_run, exit_status, f"{wall_time_secs:.1f}s"])
    table.flush()


def fetch_job_history(
    db: localdb.Connection, name: str, *, limit: Optional[int]
) -> List[Any]:
    T = models.JobRun.T
    limit_clause = f"LIMIT {limit}" if limit is not None else ""
    cursor = db.execute(
        f"""
        SELECT {T.time_run.as_string()}, {T.exit_status.as_string()}, {T.wall_time_secs.as_string()}
        FROM {T.table.as_string()}
        WHERE {T.name.as_string()} = :name
        ORDER BY {T.time_run.as_string()} DESC
        {limit_clause}
        """,
        dict(name=name),
    )
    return cursor.fetchall()


LAUNCHCTL_PATH = "/Users/iafisher/Library/LaunchAgents/com.iafisher.kg.jobserver.plist"


def main_launchctl_load() -> None:
    subprocess.run(["launchctl", "load", LAUNCHCTL_PATH], check=True)


def main_launchctl_restart() -> None:
    main_launchctl_unload()
    time.sleep(1.0)
    main_launchctl_load()


def main_launchctl_unload() -> None:
    subprocess.run(["launchctl", "unload", LAUNCHCTL_PATH], check=True)


def main_list(
    *,
    verbose: bool = False,
    disabled: Annotated[bool, command.Extra(help="Show disabled jobs.")] = False,
) -> None:
    show_disabled = disabled

    with oshelper.LockFile(server.state_lock_file_path(), exclusive=False):
        state = server.load_state_holding_lock()

    now = timehelper.now()

    disabled_count = 0
    table = tabular.Table()
    if not verbose:
        table.row(
            [
                colors.cyan("job"),
                colors.cyan("next run"),
                colors.cyan("last run"),
                colors.cyan("status"),
                colors.cyan("time"),
                colors.cyan("enabled") if show_disabled else "",
            ]
        )

    for job, is_last_iteration in iterhelper.iter_is_last(
        sorted(state.jobs, key=lambda job: job.name)
    ):
        if not job.enabled and not show_disabled:
            disabled_count += 1
            continue

        if verbose:
            show_verbose(job, now)
            if not is_last_iteration:
                print()
        else:
            time_secs = (
                f"{job.last_stats.wall_time_secs:.1f}s"
                if job.last_stats is not None
                else ""
            )
            table.row(
                [
                    colors.yellow(job.name) if job.enabled else colors.red(job.name),
                    pretty_print_datetime(job.next_scheduled_time),
                    pretty_print_datetime(job.last_run_time),
                    highlight_exit_status(job.last_exit_status),
                    time_secs,
                    colors.red("disabled") if not job.enabled else "",
                ]
            )

    if not verbose:
        table.flush()

    if disabled_count > 0:
        print()
        colors.print(f"{colors.red(pluralize(disabled_count, 'disabled job'))} hidden.")


def show_verbose(job: server.Job, now: datetime.datetime) -> None:
    colors.print(colors.yellow(job.name))
    print("- Command:", job.cmd)
    if job.last_run_time is not None:
        # TODO(2025-01): print "5 minutes ago (2025-01-05 ...)"
        print("- Last run:", job.last_run_time)
        colors.print("- Exit status:", highlight_exit_status(job.last_exit_status))
        if job.last_stats is not None:
            st = job.last_stats
            print(
                f"- Time: {st.wall_time_secs:.3f} wall, {st.user_time_secs:.3f} user, "
                + f"{st.system_time_secs:.3f} sys"
            )
            print(f"- Memory: {st.max_memory} byte(s)")
    else:
        print("- Last run: never")

    # TODO(2025-01): print "in 5 minutes (2025-01-05 ...)"
    next_run_time = job.next_scheduled_time
    colors.print(
        "- Next run:",
        (
            colors.red("never")
            if next_run_time is None
            else "now" if next_run_time <= now else next_run_time
        ),
    )

    if job.enabled:
        print("- Enabled: true")
    else:
        colors.print(f"- Enabled: {colors.red('false')}")


def highlight_exit_status(status: Optional[int]) -> str:
    if status is None:
        return "none"
    elif status != 0:
        return colors.red(str(status))
    else:
        return str(status)


def pretty_print_datetime(dt: Optional[datetime.datetime]) -> str:
    if dt is None:
        return "none"

    today = datetime.date.today()
    diff = today - dt.date()

    if abs(diff.days) < 2:
        if dt.hour == 12:
            if dt.minute == 0:
                tstr = "noon"
            else:
                tstr = f"{dt.hour}:{dt.minute:0>2}pm"
        elif dt.hour < 12:
            if dt.minute == 0:
                tstr = f"{dt.hour}am"
            else:
                tstr = f"{dt.hour}:{dt.minute:0>2}am"
        else:
            if dt.minute == 0:
                tstr = f"{dt.hour - 12}pm"
            else:
                tstr = f"{dt.hour - 12}:{dt.minute:0>2}pm"

        if diff.days == -1:
            dstr = "tomorrow"
        elif diff.days == 1:
            dstr = "yesterday"
        else:
            dstr = "today"

        return f"{dstr} at {tstr}"
    else:
        return str(dt)


def main_remove(name: Optional[str]) -> None:
    if name is None:
        name = fzf_job_name(is_enabled=None)

    with oshelper.LockFile(server.state_lock_file_path(), exclusive=True):
        state = server.load_state_holding_lock()
        job = server.remove_job_from_state(state, name)
        if job is None:
            raise KgError("job does not exist", name=name)

        server.save_state_holding_lock(state)


def main_run(
    name: Optional[str],
    *,
    debug_env: Annotated[
        bool, command.Extra(help="Print the subprocess's environment variables.")
    ] = False,
) -> None:
    if name is None:
        name = fzf_job_name()
    # TODO(2025-01): should be a better way to do this (e.g., RPC to server)
    with oshelper.LockFile(server.state_lock_file_path(), exclusive=True):
        state = server.load_state_holding_lock()
        job = server.must_find_job_in_state(state, name)
        job.run_now = True
        job.debug_env = debug_env
        server.save_state_holding_lock(state)


def fzf_job_name(*, is_enabled: Optional[bool] = True) -> str:
    with oshelper.LockFile(server.state_lock_file_path(), exclusive=False):
        state = server.load_state_holding_lock()

    return fzf.select(
        [
            job.name
            for job in state.jobs
            if is_enabled is None or is_enabled == job.enabled
        ],
        sorted=True,
    )


def main_schedule(
    config_file: Annotated[str, command.Extra(help="config file (JSON)")],
    *,
    replace: Annotated[
        bool, command.Extra(help="Replace an existing scheduled job.")
    ] = False,
    skip_existing: Annotated[bool, command.Extra(help="Ignore existing jobs.")] = False,
    skip_wrong_machine: Annotated[
        bool,
        command.Extra(
            help="Skip jobs set for a different machine, instead of failing."
        ),
    ] = False,
) -> None:
    with open(config_file, "r") as f:
        config = json.load(f)

    jobs_to_add: List[server.Job] = []

    for job_dict in config["jobs"]:
        name = job_dict["name"]
        cmd = job_dict["cmd"]
        cmd[0] = os.path.expanduser(cmd[0])

        schedule = (
            Schedule.deserialize(job_dict["schedule"])
            if job_dict.get("schedule")
            else None
        )

        machines_for_job = job_dict["machines"]
        this_machine = kgenv.get_machine()
        if this_machine not in machines_for_job:
            if skip_wrong_machine:
                print(
                    f"skipping job for another machine: {name} (machines: {machines_for_job})"
                )
                continue
            else:
                raise KgError(
                    "attempted to schedule a job on the wrong machine",
                    this_machine=this_machine,
                    machines_for_job=machines_for_job,
                )

        today = timehelper.today()
        job = server.Job(
            name=name,
            cmd=cmd,
            date_added=today,
            schedule=schedule,
            extra_path=job_dict.get("extra_path"),
            extra_pythonpath=job_dict.get("extra_pythonpath"),
            working_directory=job_dict.get("working_directory"),
            enabled=True,
            run_now=False,
            debug_env=False,
            alert_high_priority=job_dict.get("alert_high_priority", False),
        )
        jobs_to_add.append(job)

    with oshelper.LockFile(server.state_lock_file_path(), exclusive=True):
        state = server.load_state_holding_lock()

        now = timehelper.now()
        for job_to_add in jobs_to_add:
            existing_job = server.remove_job_from_state(state, job_to_add.name)
            if existing_job is not None:
                if replace:
                    print(f"replacing existing job: {job_to_add.name}")
                    job_to_add.last_run_time = existing_job.last_run_time
                    job_to_add.last_exit_status = existing_job.last_exit_status
                    job_to_add.last_stats = existing_job.last_stats
                    job_to_add.enabled = existing_job.enabled
                    job_to_add.date_added = existing_job.date_added
                    if existing_job.next_scheduled_time is not None:
                        job_to_add.next_scheduled_time = (
                            existing_job.next_scheduled_time
                        )
                    elif job_to_add.schedule is not None:
                        schedule = job_to_add.schedule.get_schedule()
                        job_to_add.next_scheduled_time = (
                            schedule.get_next_scheduled_time(now)
                        )
                else:
                    if skip_existing:
                        print(f"skipping existing job: {job_to_add.name}")
                        state.jobs.append(existing_job)
                        continue
                    else:
                        raise KgError(
                            "a job of the same name already exists",
                            name=job_to_add.name,
                        )
            else:
                if job_to_add.schedule is not None:
                    schedule = job_to_add.schedule.get_schedule()
                    job_to_add.next_scheduled_time = schedule.get_next_scheduled_time(
                        now
                    )

            state.jobs.append(job_to_add)

        server.save_state_holding_lock(state)


def main_show(name: str) -> None:
    with oshelper.LockFile(server.state_lock_file_path(), exclusive=False):
        state = server.load_state_holding_lock()
    for job in state.jobs:
        if job.name != name:
            continue

        show_verbose(job, timehelper.now())
        return

    raise KgError("job not found", name=name)


daemon_group = command.Group(help="Manage the daemon.")
daemon_group.add2(
    "kill",
    main_daemon_kill,
    help="Kill the daemon.\n\nIf the daemon is running under an OS service manager like launchd or systemd, it might immediately restart.",
)
daemon_group.add2(
    "start", main_daemon_start, help="Start the daemon.", less_logging=False
)
daemon_group.add2("status", main_daemon_status, help="Check the status of the daemon.")
daemon_group.add2(
    "test-crash",
    main_daemon_test_crash,
    help="Crash the daemon to test crash recovery.",
    less_logging=False,
)


launchctl_group = command.Group(help="Utilities for launchctl.")
launchctl_group.add2("load", main_launchctl_load, help="Load the launchctl job.")
launchctl_group.add2(
    "restart", main_launchctl_restart, help="Unload and then load the launchctl job."
)
launchctl_group.add2("unload", main_launchctl_unload, help="Unload the launchctl job.")


cmd = command.Group(help="Manage background jobs.")
cmd.add("daemon", daemon_group)
cmd.add2("disable", main_disable, help="Disable a scheduled job.")
cmd.add2(
    "enable", main_enable, help="Enable a scheduled job that was previously disabled."
)
cmd.add2("history", main_history, help="Show job history.")
cmd.add("launchctl", launchctl_group)
cmd.add2("list", main_list, help="List background jobs.")
cmd.add2("remove", main_remove, help="Remove a job from the schedule.")
cmd.add2("run", main_run, help="Manually run a job out of schedule.")
cmd.add2("schedule", main_schedule, help="Schedule a background job to run.")
cmd.add2("show", main_show, help="Show details about a job.")
