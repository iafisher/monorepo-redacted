from iafisher_foundation.command import (
    Command,
    Group,
    dispatch as _dispatch,
)
from iafisher_foundation.prelude import *
from lib import kglogging


def dispatch(
    cmd_or_group: Union[Command, Group],
    *,
    argv: Optional[List[str]] = None,
    bail_on_error: bool = True,
) -> Any:
    return _dispatch(
        cmd_or_group,
        argv=argv,
        bail_on_error=bail_on_error,
        log_init=lambda level: kglogging.init(level=level),
    )
