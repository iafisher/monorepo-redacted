import math
from typing import Literal

from iafisher import timehelper
from iafisher.prelude import *
from lib import kghttp

Direction = Literal["uptown", "downtown"]


def fetch_upcoming_arrivals(
    stop_id: str, direction: Direction, *, limit: Optional[int] = 5
) -> List[Tuple[int, str]]:
    """
    Returns list of `[mins_to_next_train, service_name]` for upcoming arrivals.
    """
    url = f"https://demo.transiter.dev/systems/us-ny-subway/stops/{stop_id}"
    response = kghttp.get(url)
    data = response.json()
    now = timehelper.now()
    arrival_times = [
        (
            timehelper.from_epoch_secs(int(d["arrival"]["time"])),
            d["trip"]["route"]["id"],
        )
        for d in data["stopTimes"]
        if _parse_headsign(d["headsign"]) == direction
    ]
    arrival_times.sort()
    return [
        (max(0, int(math.floor((t - now).total_seconds() / 60))), service)
        for t, service in (
            arrival_times[:limit] if limit is not None else arrival_times
        )
    ]


def _parse_headsign(headway: str) -> Direction:
    headway = headway.lower()
    if "downtown" in headway or "brooklyn" in headway or "bay ridge" in headway:
        return "downtown"
    elif "uptown" in headway or "manhattan" in headway or "bronx" in headway:
        return "uptown"
    else:
        raise KgError("could not parse headway as direction", headway=headway)
