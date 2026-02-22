import signal
import struct
import time
import traceback

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import dblog, emailalerts, kgenv, localdb, oshelper

from . import email_templates, models, rpc
from .server_state import (
    Job,
    JobStats,
    State,
    kg_apps_dir,
    load_state_holding_lock,
    my_appdir,
    save_state_holding_lock,
    state_lock_file_path,
)


# TODO(2025-02): Use `kgjson.with_lock` so we don't need a separate lock file.


@dataclass
class PendingJob:
    name: str
    pid: int
    log_path: pathlib.Path
    alert_high_priority: bool
    start_time_epoch_secs: float


@dataclass
class EphemeralState:
    # maps from PID to pending job
    pending_jobs_by_pid: Dict[int, PendingJob]
    signal_pipe: "SignalPipe"


@dataclass
class ChildResult:
    pid: int
    status: int
    end_time_epoch_secs: float
    rusage: Any


def run_loop(
    *,
    wakeup_interval: datetime.timedelta,
    log_interval: datetime.timedelta,
    rpc_port: int,
) -> None:
    try:
        os.chdir(kg_apps_dir())

        wakeup_every_secs = wakeup_interval.total_seconds()
        log_every_secs = log_interval.total_seconds()

        mypid = os.getpid()
        LOG.info("daemon acquiring lockfile: %s", mypid)
        with oshelper.PidLockFile(pid_lock_file_path()):
            LOG.info("daemon acquired lockfile: %s", mypid)
            last_time_logged_epoch_secs = time.time()
            ephemeral_state = set_up_with_lock()

            server = rpc.run_in_background_thread(rpc_port)
            initialize_state()

            wake_up_counter = 0
            try:
                while True:
                    wake_up_and_do_one(ephemeral_state)
                    wake_up_counter += 1
                    time_epoch_secs = time.time()
                    if time_epoch_secs - last_time_logged_epoch_secs >= log_every_secs:
                        LOG.info("woke up %d times since last log", wake_up_counter)
                        wake_up_counter = 0
                        last_time_logged_epoch_secs = time_epoch_secs

                    time.sleep(wakeup_every_secs)
            except SystemExit:
                LOG.info("shutting down RPC server")
                server.shutdown()
                raise
    except Exception:
        tb = "".join(traceback.format_exc())
        emailalerts.send_alert(
            title="jobserver crashed",
            body=email_templates.JOBSERVER_CRASHED % dict(tb=tb, machine=get_machine()),
            html=True,
            throttle_label=["jobserver_crashed"],
            high_priority=True,
        )
        raise


def initialize_state() -> None:
    now = timehelper.now()
    with oshelper.LockFile(state_lock_file_path(), exclusive=True):
        state = load_state_holding_lock()
        for job in state.jobs:
            if job.schedule is not None and job.next_scheduled_time is None:
                # TODO(2025-11): SUBWAY: catch exception and send email alert
                schedule = job.schedule.get_schedule()
                job.next_scheduled_time = schedule.get_next_scheduled_time(now)
                LOG.info(
                    "initialized next_scheduled_time of %s to %s",
                    job.name,
                    job.next_scheduled_time,
                )

        save_state_holding_lock(state)


def set_up_with_lock() -> EphemeralState:
    signal_pipe = SignalPipe()

    def sighandler(signum: int, _frame: Any):
        signal_pipe.write_signal(signum)

    signal.signal(signal.SIGCHLD, sighandler)
    signal.signal(signal.SIGHUP, sighandler)
    signal.signal(signal.SIGUSR1, sighandler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    state_lock_file_path().touch()
    return EphemeralState(pending_jobs_by_pid={}, signal_pipe=signal_pipe)


class SignalPipe:
    _read: int
    _write: int

    def __init__(self) -> None:
        r, w = os.pipe()
        self._read = r
        self._write = w
        os.set_blocking(self._read, False)

    def write_signal(self, signum: int) -> None:
        time_epoch_secs = time.time()
        os.write(self._write, bytes([signum]) + struct.pack("d", time_epoch_secs))

    def read_signal_and_time(self) -> Optional[Tuple[int, float]]:
        try:
            payload = os.read(self._read, 9)
            signum = payload[0]
            time_epoch_secs = struct.unpack("d", payload[1:])[0]
            return signum, time_epoch_secs
        except BlockingIOError:
            return None


def wake_up_and_do_one(ephemeral_state: EphemeralState) -> None:
    signal_and_time = ephemeral_state.signal_pipe.read_signal_and_time()
    if signal_and_time is not None:
        signum, signal_time_epoch_secs = signal_and_time
        handle_signal_received(ephemeral_state, signum, signal_time_epoch_secs)

    with oshelper.LockFile(state_lock_file_path(), exclusive=True):
        state = load_state_holding_lock()
        now = timehelper.now()
        jobs_to_run = get_jobs_to_run(state, ephemeral_state, now)
        for job_to_run in jobs_to_run:
            try:
                pending_job = spawn_job(job_to_run)
                dblog.log("job_run", dict(name=job_to_run.name, cmd=job_to_run.cmd))
                if pending_job.pid in ephemeral_state.pending_jobs_by_pid:
                    LOG.error("pid %s reused", pending_job.pid)
                else:
                    ephemeral_state.pending_jobs_by_pid[pending_job.pid] = pending_job
                job_to_run.last_run_time = now
                job_to_run.run_now = False
                job_to_run.debug_env = False
                if job_to_run.schedule is not None:
                    schedule = job_to_run.schedule.get_schedule()
                    job_to_run.next_scheduled_time = schedule.get_next_scheduled_time(
                        now
                    )

                # Save the state after each job is run so that we don't kick off duplicate runs
                # even if the jobserver crashes.
                #
                # TODO(2025-01): Should we save state before or after running the job? Is there a
                # race condition either way?
                save_state_holding_lock(state)
            except Exception:
                LOG.exception("exception raised while spawning job %s", job_to_run.name)
                tb = "".join(traceback.format_exc())
                emailalerts.send_alert(
                    "jobserver failed to spawn job",
                    email_templates.JOBSERVER_SPAWN_EXCEPTION
                    % dict(job=job_to_run.name, machine=get_machine(), tb=tb),
                    html=True,
                    throttle_label=["jobserver_spawn_failed"],
                    high_priority=True,
                )


def handle_signal_received(
    ephemeral_state: EphemeralState, signum: int, signal_time_epoch_secs: float
) -> None:
    if signum == signal.SIGCHLD:
        pid, status, rusage = os.wait4(-1, os.WNOHANG)
        child_result = ChildResult(
            pid=pid,
            status=os.waitstatus_to_exitcode(status),
            end_time_epoch_secs=signal_time_epoch_secs,
            rusage=rusage,
        )
        handle_child_exited(ephemeral_state, child_result)
    elif signum == signal.SIGHUP:
        LOG.info("exiting gracefully due to SIGHUP signal")
        sys.exit(0)
    elif signum == signal.SIGUSR1:
        LOG.warning("received SIGUSR1 test-crash signal, raising an exception")
        raise KgError(
            "This is a test crash triggered by receipt of SIGUSR1."
            " The daemon should restart automatically."
        )
    else:
        LOG.warning("received unexpected signal: %d", signum)


def handle_child_exited(
    ephemeral_state: EphemeralState, child_result: ChildResult
) -> None:
    pid = child_result.pid
    status = child_result.status

    if pid == 0:
        LOG.warning("waitpid(-1) returned None after SIGCHLD received")
        return

    pending_job = ephemeral_state.pending_jobs_by_pid.pop(pid, None)
    if pending_job is None:
        LOG.error("unknown pid %s of exited child", pid)
        return

    job_name = pending_job.name
    if status == 0:
        LOG.info("job %s (pid=%s) exited with status %s", job_name, pid, status)
    else:
        now = timehelper.now()
        LOG.warning("job %s (pid=%s) exited with status %s", job_name, pid, status)
        now_concise = now.strftime("%Y-%m-%d %H:%M")
        machine = kgenv.get_machine()
        try:
            emailalerts.send_alert(
                title=f"job {job_name} failed at {now_concise} on {machine}",
                body=email_templates.JOB_FAILED
                % dict(
                    job_name=job_name,
                    status=status,
                    time=now.isoformat(),
                    logfile=pending_job.log_path.as_posix(),
                    logtail=tail_file(pending_job.log_path),
                    machine=machine,
                ),
                extra_css=email_templates.JOB_FAILED_EXTRA_CSS,
                html=True,
                throttle_label=["jobserver_job_failed", job_name],
                high_priority=pending_job.alert_high_priority,
            )
        except Exception:
            LOG.error("failed to send email", exc_info=True)

    wall_time_secs = (
        child_result.end_time_epoch_secs - pending_job.start_time_epoch_secs
    )
    user_time_secs = child_result.rusage.ru_utime
    system_time_secs = child_result.rusage.ru_stime
    max_memory = child_result.rusage.ru_maxrss

    with oshelper.LockFile(state_lock_file_path(), exclusive=True):
        state = load_state_holding_lock()
        job = find_job_in_state(state, job_name)
        if job is not None:
            job.last_exit_status = status
            job.last_stats = JobStats(
                wall_time_secs=wall_time_secs,
                user_time_secs=user_time_secs,
                system_time_secs=system_time_secs,
                max_memory=max_memory,
            )
            save_state_holding_lock(state)
        else:
            LOG.error("unknown job %s in SIGCHLD handler", job_name)

    with localdb.connect() as db:
        T = models.JobRun.T
        db.execute(
            f"""
            INSERT INTO {T.table.as_string()} (
              {T.name.as_string()},
              {T.time_run.as_string()},
              {T.exit_status.as_string()},
              {T.wall_time_secs.as_string()},
              {T.user_time_secs.as_string()},
              {T.system_time_secs.as_string()},
              {T.max_memory.as_string()}
            )
            VALUES (:name, :time_run, :exit_status, :wall_time_secs, :user_time_secs, :system_time_secs, :max_memory)
            """,
            dict(
                name=pending_job.name,
                time_run=pending_job.start_time_epoch_secs,
                exit_status=status,
                wall_time_secs=wall_time_secs,
                user_time_secs=user_time_secs,
                system_time_secs=system_time_secs,
                max_memory=max_memory,
            ),
        )


def tail_file(p: pathlib.Path) -> str:
    return "".join(p.read_text().splitlines(keepends=True)[-50:])


def sigterm_handler(_signum: int, _frame: Any) -> None:
    LOG.warning("exiting because of SIGTERM signal")
    # This will raise a `SystemExit` exception that will propagate up and run clean-up functions.
    sys.exit(1)


def get_jobs_to_run(
    state: State, ephemeral_state: EphemeralState, now: datetime.datetime
) -> List[Job]:
    r: List[Job] = []
    for job in state.jobs:
        # Don't start a job that is currently running.
        if any(
            pending_job.name == job.name
            for pending_job in ephemeral_state.pending_jobs_by_pid.values()
        ):
            continue

        if not job.enabled:
            continue

        if job.run_now or (
            job.next_scheduled_time is not None and job.next_scheduled_time <= now
        ):
            r.append(job)

    return r


def spawn_job(job: Job) -> PendingJob:
    log_dir_path = job.log_dir_path()
    start_time = timehelper.now()
    log_path = log_dir_path / (start_time.isoformat() + ".log")
    os.makedirs(log_dir_path, exist_ok=True)
    # TODO(2025-01): Use `dir_fd` parameter?
    stdout_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode=0o644)

    cmd = prepare_cmd(job.cmd)
    env = prepare_env(job)

    if job.debug_env:
        os.write(stdout_fd, f"DEBUG_ENV: {env!r}\n".encode("ascii"))

    newpid = os.fork()
    if newpid == 0:
        # We are the child process.

        # Now that we are in a child process, we do not EVER want to raise an exception or
        # otherwise return to the parent. Doing so can wreak all sorts of havoc, e.g. triggering
        # the PID lockfile clean-up handler.
        try:
            # TODO(2025-01): Lots of other environment set-up to do. See APUE sec. 8.3 for list of what
            # the child process inherits from its parent.
            os.dup2(stdout_fd, 1)
            os.dup2(stdout_fd, 2)
            if job.working_directory is not None:
                os.chdir(job.working_directory)
            else:
                # TODO(2025-08): Is this the right directory to run it in?
                os.chdir(log_dir_path)
            os.execvpe(job.cmd[0], cmd, env)
        except:  # noqa: E722
            pass

        # If we've reached this point, something has gone wrong. Most likely: the command did not
        # exist.
        os._exit(127)
    else:
        # We are the parent process.
        os.close(stdout_fd)
        return PendingJob(
            name=job.name,
            pid=newpid,
            log_path=log_path,
            alert_high_priority=job.alert_high_priority,
            start_time_epoch_secs=start_time.timestamp(),
        )


def prepare_env(job: Job) -> Dict[str, str]:
    # The ":" causes Python to look for imports in the current directory, which is how
    # Python scripts in the monorepo expect to be run.
    pythonpath = ":" + ":".join(job.extra_pythonpath or [])
    # TODO(2025-01): Should child process inherit the daemon's environment?
    extra_path = ":".join(
        (job.extra_path or [])
        + [
            str(kgenv.get_ian_dir() / "bin"),
            str(kgenv.get_ian_dir() / "repos" / "current" / "bin"),
        ]
    )
    env = {
        "KG_CODE_DIR": os.environ.get("KG_CODE_DIR", ""),
        "KG_LOG_LEVEL": "info",
        "KG_MACHINE": os.environ.get("KG_MACHINE", ""),
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"] + ":" + extra_path,
        "PGHOST": os.environ.get("PGHOST", ""),
        "PYTHONPATH": pythonpath,
    }

    return env


def prepare_cmd(args: List[str]) -> List[str]:
    today = datetime.date.today()
    return [substitute_special(arg, today=today) for arg in args]


def substitute_special(arg: str, *, today: datetime.date) -> str:
    if arg == "[[date]]":
        return today.isoformat()
    elif arg == "[[yesterday]]":
        return (today + datetime.timedelta(days=-1)).isoformat()
    elif arg == "[[lastmonth]]":
        return timehelper.last_month(today).isoformat()
    else:
        return arg


def find_job_in_state(state: State, name: str) -> Optional[Job]:
    i = _find_job_in_state_index(state, name)
    return state.jobs[i] if i is not None else None


def remove_job_from_state(state: State, name: str) -> Optional[Job]:
    i = _find_job_in_state_index(state, name)
    if i is not None:
        return state.jobs.pop(i)
    else:
        return None


def _find_job_in_state_index(state: State, name: str) -> Optional[int]:
    for i, job in enumerate(state.jobs):
        if job.name == name:
            return i

    return None


def must_find_job_in_state(state: State, name: str) -> Job:
    r = find_job_in_state(state, name)
    if r is None:
        raise KgError("job does not exist", name=name)
    return r


def pid_lock_file_path() -> pathlib.Path:
    return my_appdir() / "pid.lock"


def get_machine() -> str:
    return kgenv.get_machine_opt() or "<unknown>"
