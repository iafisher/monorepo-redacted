from iafisher_foundation.prelude import *  # noqa: F401
from lib import command

from .model_info import MODEL_TO_INFO
from .model_names import ANY_FAST_MODEL, ANY_MODEL, ANY_SLOW_MODEL


def model_flag_extra(help: str = "LLM model to use") -> command.Extra:
    model_options = ", ".join(repr(m) for m in MODEL_TO_INFO)
    help = (
        help
        + f" (options: {ANY_MODEL!r}, {ANY_FAST_MODEL!r}, {ANY_SLOW_MODEL!r}, {model_options})"
    )
    return command.Extra(help=help)
