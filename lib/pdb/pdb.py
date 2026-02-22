import enum
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from enum import StrEnum
from typing import Iterable, TypeVar

from lib import kgenv
from iafisher_foundation.prelude import *

import psycopg
from psycopg import sql
from psycopg.cursor import Cursor
from psycopg.rows import RowFactory, TupleRow, tuple_row
from psycopg.abc import Params, Query


class User(StrEnum):
    ADMIN = "postgres"
    DEFAULT = "iafisher"
    READONLY = "readonly_user"


class DbName(StrEnum):
    DEFAULT = "iafisher"
    TEST = "testdb"


class TransactionMode(StrEnum):
    ONE_TRANSACTION = enum.auto()
    AUTOCOMMIT = enum.auto()
    MANUAL = enum.auto()


T = TypeVar("T")
Query2 = Union[Query, str]


class Connection:
    def __init__(self, *, user: str, dbname: str, autocommit: bool) -> None:
        self.conn = psycopg.connect(
            f"user={user} dbname={dbname}", autocommit=autocommit
        )

    def transaction(self) -> Any:
        return self.conn.transaction()

    def execute(self, query: Query2, params: Optional[Params] = None) -> None:
        self.conn.execute(self._query(query), params)

    def execute_many(self, query: Query2, params: Iterable[Params] = []) -> None:
        self.conn.cursor().executemany(self._query(query), params)

    def execute_many_and_fetch_all(
        self, query: Query2, params: Iterable[Params] = []
    ) -> List[TupleRow]:
        cursor = self.conn.cursor()
        cursor.executemany(self._query(query), params, returning=True)

        # TODO(2025-08): Once we can upgrade to psycopg 3.3, use `cursor.results()` instead
        # https://www.psycopg.org/psycopg3/docs/api/cursors.html#psycopg.Cursor.results
        results: List[TupleRow] = []
        while cursor.nextset():
            r = cursor.fetchone()
            if r is None:
                # example: INSERT ... ON CONFLICT DO NOTHING
                # `r` will be None for the rows which were not inserted because of conflict
                continue
            results.append(r)
        return results

    def fetch_one(
        self,
        query: Query2,
        params: Optional[Params] = None,
        *,
        t: RowFactory[T],
    ) -> T:
        r = self._execute(query, params, t=t).fetchone()
        if r is None:
            raise KgError(
                "expected query to return 1 row but it returned 0", query=query
            )
        return r

    def fetch_one_or_zero(
        self,
        query: Query2,
        params: Optional[Params] = None,
        *,
        t: RowFactory[T],
    ) -> Optional[T]:
        return self._execute(query, params, t=t).fetchone()

    def fetch_val(self, query: Query2, params: Optional[Params] = None) -> Any:
        return self.fetch_one(query, params, t=tuple_row)[0]

    def fetch_all(
        self,
        query: Query2,
        params: Optional[Params] = None,
        *,
        t: RowFactory[T],
    ) -> List[T]:
        return self._execute(query, params, t=t).fetchall()

    def _execute(
        self,
        query: Query2,
        params: Optional[Params],
        *,
        t: RowFactory[T],
    ) -> Cursor[T]:
        # Normally, `cursor` is used in a context manager. I read the source code for v3.2.9, and
        # the `ClientCursor` implementation (the default) doesn't actually free any external
        # resources, so it's OK to use it outside a context manager.
        #
        # https://github.com/psycopg/psycopg/blob/7671556413ca4b94911ef2032d5f1be6140c28e1/psycopg/psycopg/_cursor_base.py#L69-L79
        cursor = self.conn.cursor(row_factory=t)
        cursor.execute(self._query(query), params)
        return cursor

    @staticmethod
    def _query(query: Query2) -> Query:
        return query  # type: ignore

    def close(self) -> None:
        self.conn.close()


@contextmanager
def connect(
    *,
    user: User = User.DEFAULT,
    dbname: DbName = DbName.DEFAULT,
    transaction_mode: TransactionMode = TransactionMode.ONE_TRANSACTION,
):
    override_user_as_str = os.environ.get("KG_OVERRIDE_DB_USER")
    user_as_str = os.environ.get("KG_OVERRIDE_DB_USER", user.value)
    dbname_as_str = os.environ.get("KG_OVERRIDE_DB_NAME", dbname.value)

    if override_user_as_str is not None:
        user_as_str = override_user_as_str
    elif (
        dbname_as_str == DbName.DEFAULT.value
        and kgenv.am_i_in_dev()
        and user != User.READONLY
    ):
        user_as_str = User.READONLY.value
        LOG.info(
            "in development environment; overriding database user to %s", user_as_str
        )
    else:
        user_as_str = user.value

    conn = None
    LOG.debug("connecting to database %r as %r", dbname_as_str, user_as_str)
    try:
        match transaction_mode:
            case TransactionMode.ONE_TRANSACTION:
                autocommit = False
            case TransactionMode.AUTOCOMMIT:
                autocommit = True
            case TransactionMode.MANUAL:
                autocommit = False

        conn = Connection(user=user_as_str, dbname=dbname_as_str, autocommit=autocommit)

        match transaction_mode:
            case TransactionMode.ONE_TRANSACTION:
                with conn.transaction():
                    yield conn
            case TransactionMode.AUTOCOMMIT | TransactionMode.MANUAL:
                yield conn
    finally:
        if conn is not None:
            conn.close()


class BaseModel(ABC):
    @classmethod
    @abstractmethod
    def sql_star(cls) -> List[sql.Composable]:
        pass

    @classmethod
    @abstractmethod
    def table_name(cls) -> sql.Identifier:
        pass
