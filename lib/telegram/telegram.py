import urllib.parse
from typing import Literal

from iafisher_foundation.prelude import *
from lib import kghttp, kgjson, secrets

# https://core.telegram.org/bots/api
# https://github.com/ferranb/telegram-easy/tree/main

BASE_URL = "https://api.telegram.org/bot"


def send_message(text: str, *, token: str, chat_id: int) -> None:
    kghttp.post(
        _endpoint(token, "sendMessage"),
        json=dict(chat_id=chat_id, text=text),
        include_url_in_logs=False,  # URL contains secret token
    )


@dataclass
class User(kgjson.Base):
    # https://core.telegram.org/bots/api#user
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


@dataclass
class Chat(kgjson.Base):
    # https://core.telegram.org/bots/api#chat
    id: int
    type: Literal["private", "group", "supergroup", "channel"]
    title: Optional[str]
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    is_forum: Optional[bool]
    is_direct_messages: Optional[bool]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


@dataclass
class Message(kgjson.Base):
    # https://core.telegram.org/bots/api#message
    message_id: int
    message_thread_id: Optional[int]
    from_: Annotated[Optional[User], kgjson.Rename(name="from")]
    date: int
    chat: Chat
    edit_date: Optional[int]
    text: Optional[str]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


@dataclass
class Update(kgjson.Base):
    # https://core.telegram.org/bots/api#update
    # Some fields that I don't need are omitted.
    update_id: int
    message: Optional[Message]
    edited_message: Optional[Message]
    channel_post: Optional[Message]
    edited_channel_post: Optional[Message]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


def get_updates(
    *, token: str, timeout_secs: int, offset: Optional[int] = None
) -> List[Update]:
    http_timeout_secs = max(
        # a little padding so the HTTP connection doesn't terminate before the API timeout
        timeout_secs + 5,
        kghttp.DEFAULT_TIMEOUT_SECS,
    )
    response = kghttp.get(
        _endpoint(
            token,
            "getUpdates",
            params={"offset": str(offset), "timeout": str(timeout_secs)},
        ),
        timeout_secs=http_timeout_secs,
        include_url_in_logs=False,  # URL contains secret token
    )
    payload = response.json()
    if payload.get("ok") is not True:
        raise KgError("Telegram API returned a not-OK response", payload=payload)

    return [Update.deserialize(d) for d in payload["result"]]


def get_token() -> str:
    return secrets.get_or_raise("TELEGRAM_BOT_API_KEY")


def get_personal_id() -> int:
    return int(secrets.get_or_raise("TELEGRAM_PERSONAL_ID"))


def _endpoint(token: str, name: str, *, params: Optional[Dict[str, str]] = None) -> str:
    url = f"{BASE_URL}{token}/{name}"
    if params is not None:
        url += "?" + urllib.parse.urlencode(params)
    return url


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--get-updates", type=int, help="pass 0 to get all updates, or offset"
    )
    ap.add_argument("--message")
    args = ap.parse_args()

    token = get_token()
    if args.get_updates is not None:
        offset = args.get_updates if args.get_updates != 0 else None
        print(get_updates(token=token, timeout_secs=0, offset=offset))
    elif args.message:
        chat_id = get_personal_id()
        send_message(args.message, token=token, chat_id=chat_id)
