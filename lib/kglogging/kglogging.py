import logging

from iafisher_foundation.prelude import *
from lib import kgenv


class ConcisePathFormatter(logging.Formatter):
    """
    A log formatter that creates a concise path from the full pathname.

        .../lib/githelper/githelper.py -> lib/githelper
        .../app/obsidian/snapshot.py -> app/obsidian
    """

    @override
    def format(self, record: logging.LogRecord) -> str:
        # This seems a little expensive, but I measured it at less than a millisecond for logging
        # 50 lines.
        path = pathlib.Path(record.pathname)
        index = self._find_in_path(path, {"app", "lib"})
        if index is not None:
            record.concise_path = str(pathlib.Path(*path.parts[index:]).parent)
        else:
            record.concise_path = record.pathname
        return super().format(record)

    @staticmethod
    def _find_in_path(path: pathlib.Path, possibilities: Set[str]) -> Optional[int]:
        for i in reversed(range(len(path.parts))):
            if path.parts[i] in possibilities:
                return i
        return None


def init(*, level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.hasHandlers():
        # Tests frequently call `command.dispatch` multiple times, which in turn calls
        # `kglogging.init`.
        if kgenv.get_mode() == "test":
            return
        else:
            raise KgError("tried to initialize logging twice")

    # httpx INFO logs are spammy, especially with `lib/llm`
    logging.getLogger("httpx").setLevel(logging.WARNING)

    handler = logging.StreamHandler(sys.stderr)
    formatter = ConcisePathFormatter(
        "%(asctime)s - %(concise_path)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
