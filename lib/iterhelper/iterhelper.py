import random
from typing import TypeVar

from iafisher_foundation.prelude import *


T1 = TypeVar("T1")


def iter_is_last(xs: List[T1]) -> Generator[Tuple[T1, bool], None, None]:
    for i, x in enumerate(xs):
        is_last = i == len(xs) - 1
        yield x, is_last


T2 = TypeVar("T2")


# TODO(2025-02): better library for this?
def choose_random_weighted(xs: List[Tuple[T2, float]]) -> T2:
    if len(xs) == 0:
        raise KgError("empty list")

    xs_with_weights_summed: List[Tuple[T2, float]] = []
    sum_ = 0.0
    for x, weight in xs:
        sum_ += weight
        xs_with_weights_summed.append((x, sum_))

    r = random.random() * sum_
    for x, n in xs_with_weights_summed:
        if r <= n:
            return x

    impossible()
