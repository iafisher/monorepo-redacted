"""
A library to send email alerts.

Messages must include a throttle policy which prevents email overload. Throttled messages are
written to a queue on disk, and a periodic job sends them out one-by-one.

Messages with the same throttle label are always sent in chronological order:

- Alert 1 sent at 08:00.
- Alert 2 attempted at 08:05 and throttled.
- Alert 3 enqueued at 08:35, alert 2 sent.
- Flush job called at 08:45, alert 3 unsent because of throttling.
- Flush job called at 09:30, alert 3 sent.
"""

import dataclasses
import math
import time
import warnings

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import kgenv, kgjson, simplemail


WAIT_INTERVAL_MINS = 30


@dataclass
class Message(kgjson.Base):
    title: str
    body: str
    html: bool
    throttle_label: List[str]
    high_priority: bool
    extra_css: str


def send_alert(
    title: str,
    body: str,
    *,
    html: bool,
    throttle_label: List[str],
    high_priority: bool = False,
    extra_css: str = "",
) -> None:
    """
    Sends the alert via email (possibly throttled).
    """
    message = Message(
        title=title,
        body=body,
        html=html,
        throttle_label=throttle_label,
        high_priority=high_priority,
        extra_css=extra_css,
    )

    message_to_send = _add_and_take_from_queue(message)
    if message_to_send is not None:
        _send_alert_unconditional(message_to_send)
    else:
        LOG.warning(
            "alert %r not sent to %s due to throttling",
            message.title,
            _recipient(message),
        )


def _recipient(message: Message) -> str:
    return (
        simplemail.HIGH_PRIORITY_RECIPIENT
        if message.high_priority
        else simplemail.LOW_PRIORITY_RECIPIENT
    )


def _send_alert_unconditional(message: Message) -> None:
    if message.extra_css and not message.html:
        warnings.warn("`message.extra_css` has no effect when `message.html` is False")

    if message.html:
        body = HTML_TEMPLATE % dict(extra_css=message.extra_css, body=message.body)
    else:
        body = message.body

    simplemail.send_email(
        f"[kg] Alert: {message.title}",
        body=body,
        recipients=[_recipient(message)],
        html=message.html,
    )


def flush_throttled_alerts(force: bool) -> None:
    now_epoch_secs = math.floor(time.time())
    with State.with_lock(_path()) as lock_file:
        state = lock_file.read()
        for alert_state in state.alerts:
            n = len(alert_state.queue)
            if n == 0:
                continue

            if alert_state.is_throttled(now_epoch_secs):
                if force:
                    LOG.info(
                        "forcing flush for %r, would have been throttled otherwise",
                        alert_state.label,
                    )
                else:
                    LOG.info(
                        "not flushing messages for %r, still throttled (len(queue)=%d)",
                        alert_state.label,
                        n,
                    )
                    continue

            message = alert_state.pop_from_queue()
            _send_alert_unconditional(message)
            alert_state.last_time_sent_epoch_secs = now_epoch_secs

        lock_file.write(state)


def clear_throttled_alerts(label: List[str]) -> None:
    with State.with_lock(_path()) as lock_file:
        state = lock_file.read()
        for alert_state in state.alerts:
            if alert_state.label != label:
                continue

            n = len(alert_state.queue)
            if n == 0:
                LOG.info("skipping %s as no alerts are pending", alert_state.label)
                continue

            LOG.info("clearing %s pending alert(s) for %s", n, alert_state.label)
            alert_state.queue.clear()

        lock_file.write(state)


@dataclass
class QueueItem(kgjson.Base):
    message: Message
    original_time_epoch_secs: int


@dataclass
class AlertState(kgjson.Base):
    label: List[str]
    # `last_time_sent_epoch_secs` is updated every time an email is sent, so it can track
    # whether a new alert should be throttled or not.
    last_time_sent_epoch_secs: int
    queue: List[QueueItem] = dataclasses.field(default_factory=list)

    def pop_from_queue(self) -> Message:
        queue_item = self.queue.pop(0)
        original_time = timehelper.from_epoch_secs(queue_item.original_time_epoch_secs)
        still_pending = len(self.queue)
        if still_pending > 0:
            still_pending_msg = f"; {still_pending} still pending"
        else:
            still_pending_msg = ""
        title = (
            queue_item.message.title
            + f" (throttled since {original_time}{still_pending_msg})"
        )
        return dataclasses.replace(queue_item.message, title=title)

    def is_throttled(self, now_epoch_secs: int) -> bool:
        return now_epoch_secs < self.last_time_sent_epoch_secs + (
            WAIT_INTERVAL_MINS * 60
        )


@dataclass
class State(kgjson.Base):
    alerts: List[AlertState] = dataclasses.field(default_factory=list)


def load_state() -> State:
    try:
        return State.load(_path())
    except FileNotFoundError:
        return State()


def _add_and_take_from_queue(message: Message) -> Optional[Message]:
    """
    Adds `message` to the end of the queue and attempts to take a message from the front.

    If a message was previously sent within `WAIT_INTERVAL_MINS`, then return nothing.

    Otherwise, if the queue was empty, then this just results in `message` being returned.
    """
    now_epoch_secs = math.floor(time.time())
    with State.with_lock(_path()) as lock_file:
        state = lock_file.read()
        alert_state = _find_or_create(state, message.throttle_label)

        queue_item = QueueItem(message=message, original_time_epoch_secs=now_epoch_secs)
        if alert_state.is_throttled(now_epoch_secs):
            alert_state.queue.append(queue_item)
            r = None
        else:
            alert_state.last_time_sent_epoch_secs = now_epoch_secs
            if len(alert_state.queue) == 0:
                # queue is empty and no throttling, so we return the message unchanged
                r = message
            else:
                # push the new message to the queue and take the first queued message out
                LOG.info(
                    "adding message to back of throttle queue (title=%r, label=%r)",
                    message.title,
                    message.throttle_label,
                )
                alert_state.queue.append(queue_item)
                r = alert_state.pop_from_queue()

        lock_file.write(state)
        return r


def _path() -> PathLike:
    return kgenv.get_app_dir("emailalerts") / "state_v2.json"


def _find_or_create(state: State, label: List[str]) -> AlertState:
    for alert_state in state.alerts:
        if alert_state.label == label:
            return alert_state

    alert_state = AlertState(label=label, last_time_sent_epoch_secs=0)
    state.alerts.append(alert_state)
    return alert_state


HTML_TEMPLATE = """\
<html lang="en">
<head>
<style>
body {
  font-family: monospace;
}

%(extra_css)s
</style>
</head>
<body>
%(body)s
</body>
</html>
"""
