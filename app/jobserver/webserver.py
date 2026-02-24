from flask import render_template_string

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import localdb, oshelper, webserver

from . import rpc_web as rpc
from .server_state import (
    Job,
    State,
    load_state_holding_lock,
    log_dir_path_for_job,
    state_lock_file_path,
)


app = webserver.make_app("jobs", file=__file__)

TEMPLATE = webserver.make_template(title="kg: jobs", static_file_name="jobs")


@app.route("/")
@app.route("/job/<string:_job_name>")
@app.route("/log/<string:_job_name>/<string:_timestamp>")
def frontend_page(*args: Any, **kwargs: Any):
    return render_template_string(TEMPLATE)


@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    with oshelper.LockFile(state_lock_file_path(), exclusive=False):
        state = load_state_holding_lock()

    jobs: List[rpc.JobListItem] = []
    for job in sorted(state.jobs, key=lambda j: j.name):
        jobs.append(
            rpc.JobListItem(
                name=job.name,
                enabled=job.enabled,
                last_run_time=job.last_run_time,
                next_scheduled_time=job.next_scheduled_time,
                last_exit_status=job.last_exit_status,
                last_wall_time_secs=(
                    job.last_stats.wall_time_secs if job.last_stats else None
                ),
            )
        )

    return webserver.json_response2(rpc.JobListResponse(jobs=jobs))


@app.route("/api/job/<string:job_name>", methods=["GET"])
def api_job(job_name: str):
    with oshelper.LockFile(state_lock_file_path(), exclusive=False):
        state = load_state_holding_lock()
        job = _find_job_by_name(state, job_name)
        if job is None:
            return webserver.json_response_error(f"job not found: {job_name}"), 404

    with localdb.connect() as db:
        cursor = db.execute(
            """
            SELECT time_run, exit_status, wall_time_secs, user_time_secs, system_time_secs, max_memory
            FROM job_runs
            WHERE name = :name
            ORDER BY time_run DESC
            LIMIT 50
            """,
            dict(name=job_name),
        )
        db_runs = cursor.fetchall()

    log_dir = log_dir_path_for_job(job_name)
    runs: List[rpc.JobRunItem] = []
    for (
        time_run_epoch_secs,
        exit_status,
        wall_time_secs,
        user_time_secs,
        system_time_secs,
        max_memory,
    ) in db_runs:
        time_run = timehelper.from_epoch_secs(time_run_epoch_secs)
        log_timestamp = time_run.isoformat()
        log_path = log_dir / (log_timestamp + ".log")
        runs.append(
            rpc.JobRunItem(
                time_run=time_run,
                exit_status=exit_status,
                wall_time_secs=wall_time_secs,
                user_time_secs=user_time_secs,
                system_time_secs=system_time_secs,
                max_memory=max_memory,
                log_available=log_path.exists(),
                log_timestamp=log_timestamp,
            )
        )

    schedule_str = None
    if job.schedule is not None:
        schedule_str = job.schedule.get_type()

    response = rpc.JobDetailResponse(
        name=job.name,
        cmd=job.cmd,
        enabled=job.enabled,
        schedule=schedule_str,
        date_added=job.date_added,
        last_run_time=job.last_run_time,
        next_scheduled_time=job.next_scheduled_time,
        last_exit_status=job.last_exit_status,
        last_stats=(
            {
                "wall_time_secs": job.last_stats.wall_time_secs,
                "user_time_secs": job.last_stats.user_time_secs,
                "system_time_secs": job.last_stats.system_time_secs,
                "max_memory": job.last_stats.max_memory,
            }
            if job.last_stats
            else None
        ),
        extra_path=job.extra_path,
        extra_pythonpath=job.extra_pythonpath,
        working_directory=job.working_directory,
        alert_high_priority=job.alert_high_priority,
        runs=runs,
    )
    return webserver.json_response2(response)


@app.route("/api/log/<string:job_name>/<string:timestamp>", methods=["GET"])
def api_log(job_name: str, timestamp: str):
    log_path = log_dir_path_for_job(job_name) / (timestamp + ".log")

    if not log_path.exists():
        return webserver.json_response_error("log file not found", status=404)

    if not log_path.is_file():
        return webserver.json_response_error("log path is not a file")

    try:
        content = log_path.read_text()
    except Exception:
        LOG.exception("failed to read log file")
        return webserver.json_response_error("failed to read log", status=500)

    response = rpc.LogDetailResponse(content=content)
    return webserver.json_response2(response)


def _find_job_by_name(state: State, name: str) -> Optional[Job]:
    for job in state.jobs:
        if job.name == name:
            return job
    return None


cmd = webserver.make_command(app, default_port=7900)
