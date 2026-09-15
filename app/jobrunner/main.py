import subprocess
import tomllib

from iafisher import timehelper
from iafisher.prelude import *
from lib import command, kgenv, kgjson


"""
Job history:
    SQLite job_runs table
    with columns (name, time_run, exit_status, wall_time_secs, user_time_secs, system_time_secs, max_memory)

Job server state:
    pending jobs (to avoid starting again a job that is currently running)
    whether a job is enabled or not
"""


@dataclass
class JobSpec(kgjson.Base):
    name: str
    cmd: List[str]


@dataclass
class MachineSpec(kgjson.Base):
    jobs: List[JobSpec]

    @classmethod
    def load_from_repo(cls) -> "MachineSpec":
        machine = kgenv.get_machine()
        path = kgenv.get_code_dir() / "machines" / machine / "jobs.toml"

        with open(path, "rb") as f:
            d = tomllib.load(f)

        r = cls.deserialize(d)
        r.validate()
        return r

    def validate(self) -> None:
        job_names_seen: Set[str] = set()
        for job_spec in self.jobs:
            if job_spec.name in job_names_seen:
                raise KgError("duplicate job name", name=job_spec.name)

            job_names_seen.add(job_spec.name)

    def find_job(self, name: str) -> JobSpec:
        for job_spec in self.jobs:
            if job_spec.name == name:
                return job_spec

        raise KgError("failed to find job by name", name=name)


def main_run(jobname: str) -> None:
    machine_spec = MachineSpec.load_from_repo()
    job_spec = machine_spec.find_job(jobname)

    start_time = timehelper.now()
    log_file = (
        kgenv.get_ian_dir() / "logs" / job_spec.name / (start_time.isoformat() + ".log")
    )
    log_file.parent.mkdir(exist_ok=True, parents=True)

    # TODO: record job duration and result in SQLite database
    # TODO: set environment variables (KG_LOG_LEVEL, PYTHONUNBUFFERED, KG_DIR)
    # TODO: handle error
    with os.fdopen(
        os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode=0o644)
    ) as stdout:
        subprocess.run(job_spec.cmd, stdout=stdout, stderr=stdout)


def main_run_all() -> None:
    todo()


cmd = command.Group(help="Run and manage background jobs.")
cmd.add2("run", main_run, help="Run one job by name.")
cmd.add2("run-all", main_run_all, help="Run all jobs that are ready to run.")

if __name__ == "__main__":
    command.dispatch(cmd)
