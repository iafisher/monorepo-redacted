from iafisher_foundation.prelude import *
from typing import TextIO


class LineReader:
    f: TextIO
    pushback: Optional[str]

    def __init__(self, path: pathlib.Path) -> None:
        self.f = open(path, "r")
        self.pushback = None

    def skip_blank_lines(self) -> None:
        while True:
            line = self.read()
            if line is None:
                break
            elif line and not line.isspace():
                self.pushback = line
                break

    def read(self) -> Optional[str]:
        if self.pushback is not None:
            r = self.pushback
            self.pushback = None
            return r

        line = self.f.readline()
        return None if line == "" else line.rstrip("\n")

    def read_until(self, end: str) -> Tuple[List[str], bool]:
        end = end.rstrip("\n")
        r: List[str] = []
        found = False
        while True:
            line = self.read()
            if line is None:
                break
            elif line == end:
                found = True
                break
            else:
                r.append(line)

        return r, found

    def close(self) -> None:
        self.f.close()

    def __enter__(self) -> "LineReader":
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()
