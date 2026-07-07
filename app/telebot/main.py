import time

from iafisher_foundation.prelude import *
from lib import command, localdb, telegram


KV_LAST_OFFSET_KEY = "telebot_get_updates_last_offset"
DEFAULT_POLL_INTERVAL_SECS = 300
COOL_DOWN_INTERVAL_SECS = 5  # wait this long between successive calls to `get_updates`


def main(*, poll_interval_secs: int = DEFAULT_POLL_INTERVAL_SECS) -> None:
    bot = Telebot()
    bot.poll_forever(poll_interval_secs=poll_interval_secs)


class Telebot:
    _token: str

    def __init__(self) -> None:
        self._token = telegram.get_token()
        self._personal_id = telegram.get_personal_id()

    def poll_forever(
        self, poll_interval_secs: int = DEFAULT_POLL_INTERVAL_SECS
    ) -> None:
        with localdb.connect() as db:
            last_offset = opt_call_or(localdb.kv_get(db, KV_LAST_OFFSET_KEY), int, -1)
            LOG.info("loaded last_offset=%s from database", last_offset)

            while True:
                start_time_secs = time.time()
                timeout_secs = poll_interval_secs
                offset = last_offset + 1
                LOG.info("polling (timeout_secs=%s, offset=%s)", timeout_secs, offset)
                updates = telegram.get_updates(
                    token=self._token, timeout_secs=timeout_secs, offset=offset
                )

                if len(updates) > 0:
                    LOG.info("received updates (n=%s)", len(updates))
                    for update in updates:
                        last_offset = max(last_offset, update.update_id)
                        self._process_update(update)
                    localdb.kv_set(db, KV_LAST_OFFSET_KEY, str(last_offset))
                    LOG.info("stored last_offset=%s in the database", last_offset)
                else:
                    LOG.info("received no updates")

                sleep_secs = COOL_DOWN_INTERVAL_SECS - (time.time() - start_time_secs)
                if sleep_secs > 0:
                    LOG.info(
                        "sleeping before next API call (sleep_secs=%s, cool_down_interval_secs=%s)",
                        sleep_secs,
                        COOL_DOWN_INTERVAL_SECS,
                    )
                    time.sleep(sleep_secs)

    def _process_update(self, untrusted_update: telegram.Update) -> None:
        update_id = untrusted_update.update_id
        LOG.info("processing update (update_id=%s)", update_id)
        trusted_message = self._validate_update(untrusted_update)
        if trusted_message is None:
            return

        if trusted_message.text is None:
            LOG.info("ignoring update without `message.text` (update_id=%s)", update_id)
            return

        text = trusted_message.text.strip()
        if text == "/status":
            response_text = "Telebot is up."
        else:
            response_text = "Sorry, I didn't understand that message."

        chat_id = trusted_message.chat.id
        LOG.info(
            "sending response message (update_id=%s, chat_id=%s, length=%s)",
            update_id,
            chat_id,
            len(response_text),
        )
        telegram.send_message(response_text, token=self._token, chat_id=chat_id)
        LOG.info("sent response message (update_id=%s, chat_id=%s)", update_id, chat_id)

    def _validate_update(
        self, untrusted: telegram.Update
    ) -> Optional[telegram.Message]:
        update_id = untrusted.update_id

        if untrusted.message is None:
            LOG.info("ignoring update without `message` (update_id=%s)", update_id)
            return None

        if untrusted.message.from_ is None:
            LOG.info(
                "ignoring update without `message.from` (update_id=%s)",
                untrusted.update_id,
            )
            return None

        if untrusted.message.from_.id != self._personal_id:
            LOG.info(
                "ignoring update from unknown sender (update_id=%s, sender=%r)",
                untrusted.message.from_,
            )
            return None

        return untrusted.message


cmd = command.Command.from_function(
    main, help="Run the Telegram bot.", less_logging=False
)

if __name__ == "__main__":
    command.dispatch(cmd)
