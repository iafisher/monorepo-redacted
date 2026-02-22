import fcntl
import uuid
from typing import IO, Self

from iafisher_foundation.prelude import *


def replace_file(p: PathLike, contents: Union[str, bytes]) -> None:
    tmppath = _tmppath_for(p)
    if isinstance(contents, str):
        tmppath.write_text(contents)
    else:
        tmppath.write_bytes(contents)
    os.rename(tmppath, p)


def _tmppath_for(p: PathLike) -> pathlib.Path:
    return pathlib.Path(p).parent / f"kg-tempfile-{uuid.uuid4()}"


class LockFile:
    path: PathLike
    mode: str
    exclusive: bool
    f: Optional[IO[Any]]

    def __init__(self, path: PathLike, *, mode: str = "r", exclusive: bool) -> None:
        self.path = path
        self.mode = mode
        self.exclusive = exclusive
        self.f = None

    def acquire(self, *, wait: bool = True) -> None:
        self.f = open(self.path, self.mode)
        fcntl.flock(
            self.f.fileno(),
            (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH)
            | (0 if wait else fcntl.LOCK_NB),
        )

    def release(self) -> None:
        if self.f is not None:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            self.f.close()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.release()


class PidLockFile:
    path: PathLike
    fd: Optional[int]

    def __init__(self, path: PathLike) -> None:
        self.path = path
        self.fd = None

    def __enter__(self) -> "PidLockFile":
        # TODO(2025-02): move to `__init__`?
        self.fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, mode=0o666)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise KgError("PID lockfile already taken", path=self.path) from None

        os.truncate(self.fd, 0)

        pid = os.getpid()
        os.write(self.fd, str(pid).encode("ascii") + b"\n")
        os.fsync(self.fd)
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        if self.fd is not None:
            os.unlink(self.path)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def get_boolean_env_var(key: str, *, default: Optional[bool] = None) -> bool:
    strval = os.environ.get(key)
    if strval is None:
        if default is not None:
            return default
        else:
            raise KgError("environment variable not set", var=key)

    if strval == "1":
        return True
    elif strval == "0":
        return False
    else:
        raise KgError(
            "boolean environment variable must be set to '1' or '0'",
            var=key,
            val=strval,
        )


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
