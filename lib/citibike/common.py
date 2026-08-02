from typing import NewType

from iafisher.prelude import *


StationId = NewType("StationId", str)


@dataclass
class Station:
    station_id: StationId
    official_name: str
    nickname: str


@dataclass
class StationStatus:
    station_id: StationId
    num_regular_bikes_available: int
    num_docks_available: int
    is_renting: bool
    is_returning: bool
