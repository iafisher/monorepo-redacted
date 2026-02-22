from typing import Annotated

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, emailalerts


def main_clear(label: str) -> None:
    # TODO(2026-02): This is a little awkward. Maybe just represent labels as strings?
    label_as_list = label.split()
    emailalerts.clear_throttled_alerts(label_as_list)


def main_flush(
    *,
    force: Annotated[
        bool, command.Extra(help="send messages even if they would still be throttled")
    ],
) -> None:
    emailalerts.flush_throttled_alerts(force=force)


def main_list() -> None:
    state = emailalerts.load_state()
    for alert_state in state.alerts:
        n = len(alert_state.queue)
        if n == 0:
            continue

        throttled_since = timehelper.from_epoch_secs(
            alert_state.queue[0].original_time_epoch_secs
        )
        print(
            f"{alert_state.label!r}: {pluralize(n, 'message')} since {throttled_since}"
        )


def main_send_test() -> None:
    emailalerts.send_alert(
        "Test alert",
        "This is a test alert sent by the `emailalerts` command.",
        html=False,
        throttle_label=["emailalerts_send_test"],
    )


cmd = command.Group()
cmd.add2("clear", main_clear, help="Clear throttled alerts without sending them.")
cmd.add2("flush", main_flush, help="Flush throttled email alerts.")
cmd.add2("list", main_list, help="List email alerts that are currently throttled.")
cmd.add2("send-test", main_send_test, help="Send a test alert.")

if __name__ == "__main__":
    command.dispatch(cmd)
