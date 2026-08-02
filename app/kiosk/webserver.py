import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from flask import render_template_string

from iafisher import timehelper
from iafisher.prelude import *  # noqa: F401
from lib import citibike, subway, webserver

app = webserver.make_app("kiosk", file=__file__)


TEMPLATE = webserver.make_template(title="kg: kiosk", static_file_name="kiosk")


INDEX_PAGE = """\
<main class="page-index">
  <div class="row">
    %(subway_html)s
    %(bikes_html)s
  </div>
  <p class="when-loaded">Page loaded at <strong>%(time)s</strong>. <a href="/">Reload</a>.</p>
</main>

<script>
const RELOAD_AFTER_MILLIS = 45000;

const timeLoadedMillis = Date.now();
document.addEventListener('pointerdown', (event) => {
  // On touch, reload the page if loaded more than RELOAD_AFTER_MILLIS ago.
  //
  // This is so that the initial touch on the touch display causes the page to be
  // refreshed.
  if (Date.now() - timeLoadedMillis >= RELOAD_AFTER_MILLIS) {
    window.location.reload();
  }
});
</script>
"""


@app.route("/")
def index_page():
    stop = subway.stops.COURT_ST
    direction = "uptown"

    with ThreadPoolExecutor() as executor:
        subway_arrivals_future = executor.submit(
            subway.fetch_upcoming_arrivals, stop.id, direction
        )
        citibike_station_statuses_future = executor.submit(
            _fetch_citibike_station_statuses,
            [citibike.stations.HOME, citibike.stations.GYM1, citibike.stations.GYM2],
        )

        try:
            subway_arrivals = subway_arrivals_future.result()
        except Exception:
            eprint(traceback.format_exc())
            subway_arrivals = None

        try:
            citibike_station_statuses = citibike_station_statuses_future.result()
        except Exception:
            eprint(traceback.format_exc())
            citibike_station_statuses = None

    now = timehelper.now()

    if subway_arrivals is not None:
        subway_html = _render_subway_html(now, subway_arrivals)
    else:
        subway_html = _render_failed_to_fetch_error("subway")

    if citibike_station_statuses is not None:
        bikes_html = _render_bikes_html(citibike_station_statuses)
    else:
        bikes_html = _render_failed_to_fetch_error("bikes")

    return render_template_string(
        TEMPLATE,
        content_html=INDEX_PAGE
        % dict(
            bikes_html=bikes_html,
            subway_html=subway_html,
            time=_time_string(),
        ),
    )


# tuples of (min_to_next_train, service)
SubwayArrivals = List[Tuple[int, str]]


def _render_subway_html(now: dt.datetime, arrivals: SubwayArrivals) -> str:
    next_two_times = _get_next_two_subway_times(arrivals)
    if len(next_two_times) == 0:
        next_two_times_html = "No trains scheduled."
    elif len(next_two_times) == 1:
        next_two_times_html = (
            f'Leave <span class="when">{_leave_when(next_two_times[0])}</span>.'
        )
    else:
        next_two_times_html = (
            f'Leave <span class="when">{_leave_when(next_two_times[0])}</span>'
            f' or <span class="when">{_leave_when(next_two_times[1])}</span>.'
        )

    rows = "".join(
        f'<tr><td class="service">{service}</td>'
        f'<td class="time {_classify_min_to_next_train(min_to_next_train)}">{min_to_next_train}m</td>'
        f'<td class="arrival">{_hh_mm(now, min_to_next_train)}</td></tr>'
        for min_to_next_train, service in arrivals
    )

    return (
        f'<div class="subway"><div class="next-times">{next_two_times_html}</div>'
        f"<table><tbody>{rows}</table></tbody></div>"
    )


def _leave_when(mins_until_departure: int) -> str:
    mins_to_leave = mins_until_departure - MINS_TO_STATION
    if mins_to_leave < 0:
        return "[error: too late]"
    elif mins_to_leave == 0:
        return "now"
    else:
        return f"in {mins_to_leave} m"


def _render_bikes_html(
    station_statuses: List[Tuple[str, citibike.StationStatus]]
) -> str:
    rows = "".join(
        _station_status_html(nickname, status) for nickname, status in station_statuses
    )
    return f'<div class="bikes">{rows}</div>'


def _render_failed_to_fetch_error(name: str) -> str:
    return f'<div class="error">Sorry, there was an error rendering the {name!r} widget.</div>'


def _fetch_citibike_station_statuses(
    stations: List[citibike.Station],
) -> List[Tuple[str, citibike.StationStatus]]:
    return list(
        zip(
            [station.nickname for station in stations],
            citibike.fetch_station_statuses(
                [station.station_id for station in stations]
            ),
        )
    )


def _hh_mm(now: dt.datetime, plus_minutes: int) -> str:
    return (now + dt.timedelta(minutes=plus_minutes)).strftime("%I:%M")


def _station_status_html(name: str, station_status: citibike.StationStatus) -> str:
    if not station_status.is_renting or not station_status.is_returning:
        status_html = "offline"
    else:
        status_html = (
            pluralize(station_status.num_regular_bikes_available, "bike")
            + ", "
            + pluralize(station_status.num_docks_available, "dock")
        )

    return f"""\
<div class="station">
  <span class="name">{name}</span>
  <span class="status">{status_html}</span>
</div>
"""


# Add a back link to the main page.
#
# This is important on the kiosk as the webpage is maximized and navigation is otherwise
# difficult.
PAGE_NOT_FOUND = """\
<main class="page-not-found">
  <h1>Page not found</h1>
  <p>The requested URL was not found on the server.</p>
  <p><a href="/">Click here</a> to return to the main page.</p>
</main>
"""


@app.errorhandler(404)
def page_not_found(_error: Any):
    return render_template_string(TEMPLATE, content_html=PAGE_NOT_FOUND)


TrainClassification = Literal["too-late", "hurry", "ok"]


# how many minutes to get from my apartment to the subway platform
MINS_TO_STATION = 7


def _classify_min_to_next_train(mins: int) -> TrainClassification:
    if mins < MINS_TO_STATION:
        return "too-late"
    elif mins < MINS_TO_STATION + 2:
        return "hurry"
    else:
        return "ok"


def _get_next_two_subway_times(arrivals: SubwayArrivals) -> List[int]:
    not_too_late = [
        mins for mins, _ in arrivals if _classify_min_to_next_train(mins) != "too-late"
    ]
    return not_too_late[:2]


def _time_string() -> str:
    return _time_string_from(timehelper.now())


def _time_string_from(timestamp: dt.datetime) -> str:
    return timestamp.strftime("%b %d, %I:%M:%S %p")


cmd = webserver.make_command(app, default_port=8100)
