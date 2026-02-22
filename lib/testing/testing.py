import os
import pathlib
import subprocess
import textwrap
import unittest
import uuid
from io import StringIO
from typing import Any, Callable
from typing_extensions import override
from unittest.mock import patch

from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import sh0

import expecttest
import psycopg

S = textwrap.dedent
TESTING_ENV_VAR = "KG_TESTING"


# TODO(2025-07): Move into lib/kgenv?
def am_i_testing() -> bool:
    # would be nice to use `oshelper.get_boolean_env_var` here, but that creates a circular
    # dependency.
    return os.environ.get(TESTING_ENV_VAR) == "1"


class Base(expecttest.TestCase):
    @classmethod
    @override
    def setUpClass(cls):
        os.environ[TESTING_ENV_VAR] = "1"

    def assertStdout(self, expected: str, actual_callable: Callable[[], Any]) -> None:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            actual_callable()
            self.assertEqual(S(expected), mock_stdout.getvalue())


class BaseExpectStdout(Base):
    @override
    def setUp(self):
        self._stdout = StringIO()
        self._patch = patch("sys.stdout", new=self._stdout)
        self._patch.start()

    @override
    def tearDown(self):
        self._patch.stop()

    def stdout(self) -> str:
        return self._stdout.getvalue()


class BaseWithDatabase(Base):
    # TODO(2025-07): Run with special test user.
    DB_USER = "iafisher"

    @classmethod
    @override
    def setUpClass(cls):
        super().setUpClass()
        cls.dbname = f"test-{uuid.uuid4()}"
        os.environ["KG_OVERRIDE_DB_USER"] = cls.DB_USER
        os.environ["KG_OVERRIDE_DB_NAME"] = cls.dbname
        # See app/db/main.py for similar command.
        # `-s` means copy schema only, no data.
        sh0(
            f"createdb {cls.dbname} --owner {cls.DB_USER}"
            " && pg_dump -Fc -s iafisher"
            f" | pg_restore -d {cls.dbname} -s --user postgres"
        )

    @classmethod
    @override
    def tearDownClass(cls) -> None:
        del os.environ["KG_OVERRIDE_DB_USER"]
        del os.environ["KG_OVERRIDE_DB_NAME"]

        super().tearDownClass()
        sh0(f"dropdb {cls.dbname}")

    @classmethod
    def run_sql(cls, sql_path: PathLike) -> None:
        with psycopg.connect(f"user={cls.DB_USER} dbname={cls.dbname}") as conn:
            conn.execute(pathlib.Path(sql_path).read_text())  # type: ignore[arg-type]


_datetime_regex = lazy_re(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?(?:-[0-9]{2}:[0-9]{2})?"
)


def expunge_datetimes(s: str) -> str:
    # Replacing the datetime with an equal number of Xs ensures that formatted output remains
    # aligned properly. However, it will cause flakiness if the test produces datetimes that
    # vary in length.
    return _datetime_regex.get().sub(lambda m: "X" * len(m.group(0)), s)


def shell(*words: Union[str, PathLike]) -> str:
    proc = subprocess.run(words, check=True, text=True, stdout=subprocess.PIPE)
    return proc.stdout
