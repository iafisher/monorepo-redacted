from typing import Annotated

from iafisher_foundation.prelude import *
from lib import command, kghttp


TIMEOUT_SECS = 10


def main(
    url: str,
    *,
    keyphrase: Annotated[
        Optional[str],
        command.Extra(
            help="also check that this keyphrase appears in the HTTP response"
        ),
    ] = None,
) -> None:
    if not is_it_up("http://1.1.1.1", print_status=False):
        LOG.warning("not connected to the Internet, bailing")
        return

    if not is_it_up(url, print_status=True, keyphrase=keyphrase):
        sys.exit(1)


def is_it_up(url: str, *, print_status: bool, keyphrase: Optional[str] = None) -> bool:
    try:
        r = kghttp.get(url, timeout_secs=TIMEOUT_SECS, retry_config=None)
    except kghttp.KgHttpError as e:
        if print_status:
            print(f"unreachable: {url} ({e})")
        return False
    else:
        if not r.ok:
            if print_status:
                print(f"HTTP error {r.status_code}: {url}")
            return False

        if keyphrase is not None and keyphrase not in r.text:
            if print_status:
                print(f"response missing keyphrase {keyphrase!r}: {url}")
            return False

        if print_status:
            print(f"ok: {url}")
        return True


cmd = command.Command.from_function(main, help="Check if a website is online.")

if __name__ == "__main__":
    command.dispatch(cmd)
