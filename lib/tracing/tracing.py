import contextlib
import json
import time

from lib import oshelper
from iafisher.prelude import *


ENVVAR = "KG_TRACING"
IS_TRACING_ENABLED = lazy(lambda: oshelper.get_boolean_env_var(ENVVAR, default=False))

CURRENT_TRACE: List[StrDict] = []


@contextlib.contextmanager
def trace(name: str, *, log: bool = True):
    if log:
        LOG.info("start: %s", name)

    if not IS_TRACING_ENABLED.get():
        yield
    else:
        # https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview?tab=t.0#heading=h.uxpopqvbjezh
        CURRENT_TRACE.append(
            dict(name=name, cat="", ph="B", ts=_time_us(), pid=1, tid=1, args={})
        )
        try:
            yield
        finally:
            CURRENT_TRACE.append(
                dict(name=name, cat="", ph="E", ts=(_time_us()), pid=1, tid=1, args={})
            )

    if log:
        LOG.info("end:   %s", name)


def _time_us() -> int:
    return time.time_ns() // 1000


def save(filepath: PathLike) -> None:
    with open(filepath, "w") as f:
        json.dump(CURRENT_TRACE, f)


if __name__ == "__main__":
    os.environ[ENVVAR] = "1"
    with trace("all"):
        n = 50_000
        r, w = os.pipe()
        with trace("read_from_urandom"):
            b = os.urandom(n)

        with trace("write_to_pipe"):
            os.write(w, b)

        with trace("read_from_pipe"):
            os.read(r, n)

        with trace("sleep"):
            time.sleep(0.01)

    filepath = pathlib.Path("test-trace.json").absolute()
    save(filepath)
    print(f"Go to https://ui.perfetto.dev/ and open {filepath}")
