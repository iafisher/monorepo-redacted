import sqlite3

from lib import kgenv
from iafisher_foundation.prelude import *  # noqa: F401


Connection = sqlite3.Connection


# TODO(2025-12): Support `TransactionMode` like `pgdb`


def connect(*, path: Optional[PathLike] = None) -> Connection:
    # https://iafisher.com/blog/2021/10/using-sqlite-effectively-in-python
    conn = sqlite3.connect(opt_or_thunk(path, lambda: get_path()), isolation_level=None)
    conn.execute("PRAGMA foreign_keys = 1")
    return conn


def get_path() -> pathlib.Path:
    return get_path_for_mode(kgenv.get_mode())


def get_path_for_mode(mode: kgenv.Mode) -> pathlib.Path:
    return kgenv.get_ian_dir_for_mode(mode) / "local.db"


def kv_get(db: Connection, key: str) -> Optional[str]:
    cursor = db.cursor()
    cursor.execute("SELECT value FROM kv WHERE key = :key", dict(key=key))
    row_opt = cursor.fetchone()
    return row_opt[0] if row_opt is not None else None


def kv_set(db: Connection, key: str, value: str) -> None:
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO kv(key, value) VALUES (:key, :value) ON CONFLICT DO UPDATE SET value = :value",
        dict(key=key, value=value),
    )
