import json

from app.jobserver.scheduler import Schedule

from lib import kgenv, kgjson, oshelper
from iafisher_foundation.prelude import *


@dataclass
class JobStats(kgjson.Base):
    wall_time_secs: float
    user_time_secs: float
    system_time_secs: float
    max_memory: int


@dataclass
class Job(kgjson.Base):
    # ATTENTION: any field added here must also be added to `main_schedule` in `./cli.py`
    name: str
    cmd: List[str]
    date_added: datetime.date
    schedule: Optional[Schedule]
    enabled: bool
    run_now: bool
    debug_env: bool = False
    alert_high_priority: bool = False
    machines: Optional[List[str]] = None
    extra_path: Optional[List[str]] = None
    extra_pythonpath: Optional[List[str]] = None
    working_directory: Optional[str] = None
    last_run_time: Optional[datetime.datetime] = None
    next_scheduled_time: Optional[datetime.datetime] = None
    last_exit_status: Optional[int] = None
    last_stats: Optional[JobStats] = None

    def log_dir_path(self) -> pathlib.Path:
        return log_dir_path_for_job(self.name)


def log_dir_path_for_job(name: str) -> pathlib.Path:
    return kgenv.get_ian_dir() / "logs" / name


@dataclass
class State(kgjson.Base):
    jobs: List[Job]


def kg_apps_dir() -> pathlib.Path:
    return kgenv.get_ian_dir() / "apps"


def my_appdir() -> pathlib.Path:
    return kg_apps_dir() / "jobserver"


def state_file_path() -> pathlib.Path:
    return my_appdir() / "state.json"


def state_lock_file_path() -> pathlib.Path:
    return my_appdir() / "state.lock"


def load_state_holding_lock() -> State:
    try:
        with open(state_file_path(), "r") as f:
            json_d = json.load(f)
            return State.deserialize(json_d)
    except FileNotFoundError:
        return State(jobs=[])


def save_state_holding_lock(state: State) -> None:
    oshelper.replace_file(state_file_path(), State.serialize(state))
