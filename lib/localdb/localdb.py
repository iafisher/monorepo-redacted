import sqlite3

from lib import kgenv
from iafisher_foundation.prelude import *  # noqa: F401


Connection = sqlite3.Connection


# TODO(2025-12): Support `TransactionMode` like `pdb`


def connect() -> Connection:
    # https://iafisher.com/blog/2021/10/using-sqlite-effectively-in-python
    conn = sqlite3.connect(kgenv.get_ian_dir() / "local.db", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = 1")
    return conn
