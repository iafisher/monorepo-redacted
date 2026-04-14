import json
import traceback

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import kgenv, localdb, oshelper

from . import models


def log(event: str, payload: StrDict) -> None:
    try:
        info = _prepare_log(event, payload)
        if info is None:
            return

        with localdb.connect() as db:
            _log(db, info)
    except Exception:
        LOG.error("dblog.log failed with error", exc_info=True)


@dataclass
class LogInfo:
    event: str
    payload: str
    app: str
    lib: Optional[str]


def _prepare_log(event: str, payload: StrDict) -> Optional[LogInfo]:
    if kgenv.get_mode() == "test" or oshelper.get_boolean_env_var(
        "KG_DBLOG_DISABLE", default=False
    ):
        return None

    info = _find_app_and_lib(traceback.extract_stack())
    if info is None:
        LOG.error(
            "dblog unable to extract app/lib info from traceback (message: %s: %r)",
            event,
            payload,
        )
        return None

    app, lib = info
    if lib is not None:
        LOG.info("%s: %s: %s: %r", app, lib, event, payload)
    else:
        LOG.info("%s: %s: %r", app, event, payload)

    try:
        payload_as_str = json.dumps(payload)
    except TypeError:
        LOG.error(
            "dblog unable to encode payload as object (message: %s: %r)",
            event,
            payload,
            exc_info=True,
        )
        return None

    return LogInfo(event=event, payload=payload_as_str, app=app, lib=lib)


def _log(db: localdb.Connection, info: LogInfo) -> None:
    T = models.Entry.T
    # SQLite has less sophisticated time zone handling than Postgres, so best to store
    # everything as a UTC timestamp to avoid confusion.
    time_created = timehelper.utcnow()
    machine = kgenv.get_machine()
    db.execute(
        f"""
        INSERT INTO {T.table.as_string()} (
          {T.app.as_string()},
          {T.lib.as_string()},
          {T.machine.as_string()},
          {T.event.as_string()},
          {T.payload.as_string()},
          {T.time_created.as_string()}
        )
        VALUES (:app, :lib, :machine, :event, :payload, :time_created)
        """,
        dict(
            app=info.app,
            lib=info.lib,
            machine=machine,
            event=info.event,
            payload=info.payload,
            time_created=time_created,
        ),
    )


def _find_app_and_lib(
    traceback: traceback.StackSummary,
) -> Optional[Tuple[str, Optional[str]]]:
    lib = None
    app = None
    for frame in reversed(traceback[:-1]):
        info = _get_app_or_lib(frame.filename)
        if info is None:
            continue

        if info[0] == "lib":
            if info[1] not in ("command", "dblog") and lib is None:
                lib = info[1]
        else:
            if app is None:
                app = info[1]

        if app is not None:
            # libs should never call into apps, so once we've found the app we're done.
            break

    if app is None:
        return None
    else:
        return app, lib


def _get_app_or_lib(filename: str) -> Optional[Tuple[str, str]]:
    parts = pathlib.Path(filename).parts
    for i in reversed(range(1, len(parts))):
        if parts[i - 1] in ("app", "lib"):
            return parts[i - 1], parts[i]

    return None
