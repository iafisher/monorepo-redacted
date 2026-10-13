import contextlib
import tempfile
import time

from app.jev.main import review_one_diff
from iafisher.prelude import *
from iafisher.scripting import q, sh1


def create_diff(before: str, after: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        with contextlib.chdir(tmpdir):
            a = pathlib.Path("a.txt")
            a.write_text(before)
            b = pathlib.Path("b.txt")
            b.write_text(after)
            return sh1(
                f"git diff -U30 --no-index {q(a.as_posix())} {q(b.as_posix())}",
                check=False,
            )


# `transaction2 = ... params.txid1` should be `params.txid2`
PARALLEL_STRUCTURE_ERROR = """\
def pair(db: pgdb.Connection, params: Pair) -> None:
    transaction1 = storage.fetch_transaction(db, params.txid1)
    transaction2 = storage.fetch_transaction(db, params.txid1)

    quarter1 = types.Quarter.of_date(transaction1.date)
    quarter2 = types.Quarter.of_date(transaction2.date)
    if quarter1 != quarter2:
        raise KgError(
            "cannot pair transactions across quarters",
            transaction1=transaction1,
            transaction2=transaction2,
        )

    posting1 = transaction1.opposite_side_of("error")
    posting2 = transaction2.opposite_side_of("error")

    if posting1.amount_usd != -posting2.amount_usd:
        raise KgError(
            "opposite sides of `pair` must have inverse amounts",
            posting1=posting1,
            posting2=posting2,
        )

    new_transaction = types.Transaction(
        txid=transaction1.txid,
        date=transaction1.date,
        memo=_update_memo(transaction1, "manual: pair"),
        postings=[posting1, posting2],
    )
    entry_time = timehelper.now()
    storage.delete_transaction(db, params.txid2)
    storage.replace_transaction(
        db, params.txid1, new_transaction, entry_time=entry_time
    )
"""

# "tranasctions" --> "transactions"
MISSPELLING = """\
def pair(db: pgdb.Connection, params: Pair) -> None:
    transaction1 = storage.fetch_transaction(db, params.txid1)
    transaction2 = storage.fetch_transaction(db, params.txid2)

    quarter1 = types.Quarter.of_date(transaction1.date)
    quarter2 = types.Quarter.of_date(transaction2.date)
    if quarter1 != quarter2:
        raise KgError(
            "cannot pair tranasctions across quarters",
            transaction1=transaction1,
            transaction2=transaction2,
        )

    posting1 = transaction1.opposite_side_of("error")
    posting2 = transaction2.opposite_side_of("error")

    if posting1.amount_usd != -posting2.amount_usd:
        raise KgError(
            "opposite sides of `pair` must have inverse amounts",
            posting1=posting1,
            posting2=posting2,
        )

    new_transaction = types.Transaction(
        txid=transaction1.txid,
        date=transaction1.date,
        memo=_update_memo(transaction1, "manual: pair"),
        postings=[posting1, posting2],
    )
    entry_time = timehelper.now()
    storage.delete_transaction(db, params.txid2)
    storage.replace_transaction(
        db, params.txid1, new_transaction, entry_time=entry_time
    )
"""

OK = """\
def pair(db: pgdb.Connection, params: Pair) -> None:
    transaction1 = storage.fetch_transaction(db, params.txid1)
    transaction2 = storage.fetch_transaction(db, params.txid2)

    quarter1 = types.Quarter.of_date(transaction1.date)
    quarter2 = types.Quarter.of_date(transaction2.date)
    if quarter1 != quarter2:
        raise KgError(
            "cannot pair transactions across quarters",
            transaction1=transaction1,
            transaction2=transaction2,
        )

    posting1 = transaction1.opposite_side_of("error")
    posting2 = transaction2.opposite_side_of("error")

    if posting1.amount_usd != -posting2.amount_usd:
        raise KgError(
            "opposite sides of `pair` must have inverse amounts",
            posting1=posting1,
            posting2=posting2,
        )

    new_transaction = types.Transaction(
        txid=transaction1.txid,
        date=transaction1.date,
        memo=_update_memo(transaction1, "manual: pair"),
        postings=[posting1, posting2],
    )
    entry_time = timehelper.now()
    storage.delete_transaction(db, params.txid2)
    storage.replace_transaction(
        db, params.txid1, new_transaction, entry_time=entry_time
    )
"""


def time_and_review_one_diff(after: str, before: str = "") -> Any:
    before_ns = time.perf_counter_ns()
    result = review_one_diff(create_diff(before, after))
    after_ns = time.perf_counter_ns()
    print(f"time: {(after_ns - before_ns) / 1_000_000_000:.3f}s", file=sys.stderr)
    return result


if __name__ == "__main__":
    print("=== parallel structure ===")
    print(time_and_review_one_diff(PARALLEL_STRUCTURE_ERROR))

    print("=== misspelling ===")
    print(time_and_review_one_diff(MISSPELLING))

    print("=== clean diff ===")
    print(time_and_review_one_diff(OK))
