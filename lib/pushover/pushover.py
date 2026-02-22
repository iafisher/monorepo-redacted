from iafisher_foundation.prelude import *
from lib import dblog, kghttp, secrets


def notify(message: str, *, title: Optional[str] = None) -> None:
    api_key = secrets.get("PUSHOVER_API_KEY")
    user_key = secrets.get("PUSHOVER_USER_KEY")
    payload = dict(token=api_key, user=user_key, message=message)
    if title is not None:
        payload["title"] = title

    kghttp.post("https://api.pushover.net/1/messages.json", json=payload)
    dblog.log("notification_sent", dict(message=message, title=title))
