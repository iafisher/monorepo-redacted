from lib import secrets
from iafisher_foundation.prelude import *  # noqa: F401


HTTP_API_KEY_HEADER = "X-Iafisher-Api-Key"
DO_NOT_PUBLISH_PROPERTY = "iafisher-do-not-publish"
CODE_PATH = pathlib.Path.home() / "Code" / "iafisher.com"


def ensure_api_key(*, local: bool) -> str:
    if local:
        return secrets.get_or_raise("IAN_IAFISHER_DEV_API_KEY")
    else:
        return secrets.get_or_raise("IAN_IAFISHER_API_KEY")
