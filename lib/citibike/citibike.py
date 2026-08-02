from iafisher.prelude import *
from lib import kghttp

from .common import StationId, StationStatus
from .stations import GYM1, GYM2, HOME


# Reference:
#   - https://citibikenyc.com/system-data
#   - https://github.com/MobilityData/gbfs/blob/master/gbfs.md


def fetch_station_statuses(station_ids: List[StationId]) -> List[StationStatus]:
    response = kghttp.get("https://gbfs.lyft.com/gbfs/2.3/bkn/en/station_status.json")

    station_id_to_status: Dict[StationId, StationStatus] = {}
    for station in response.json()["data"]["stations"]:
        station_id = station["station_id"]
        if station_id in station_ids:
            station_id_to_status[station_id] = _create_station_status(station)

    r: List[StationStatus] = []
    for station_id in station_ids:
        try:
            r.append(station_id_to_status[station_id])
        except KeyError:
            raise KgError("station status missing", station_id=station_id)
    return r


REGULAR_BIKE_TYPE_ID = "1"


def _create_station_status(data: StrDict) -> StationStatus:
    num_regular_bikes_available = 0
    for availability in data["vehicle_types_available"]:
        if availability["vehicle_type_id"] == REGULAR_BIKE_TYPE_ID:
            num_regular_bikes_available = availability["count"]
            break

    return StationStatus(
        station_id=data["station_id"],
        num_regular_bikes_available=num_regular_bikes_available,
        num_docks_available=data["num_docks_available"],
        is_renting=data["is_renting"] == 1,
        is_returning=data["is_returning"] == 1,
    )


def fetch_station_status(station_id: StationId) -> StationStatus:
    return fetch_station_statuses([station_id])[0]


if __name__ == "__main__":
    print("Home: ", fetch_station_status(HOME.station_id))
    print("Gym 1:", fetch_station_status(GYM1.station_id))
    print("Gym 2:", fetch_station_status(GYM2.station_id))
