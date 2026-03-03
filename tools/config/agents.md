You are working inside a monorepo of Python code. It is organized as follows:

- `app/` holds applications (mostly command-line tools, but also some web applications and
  Obsidian plugins).
- `frontend/` has frontend web code (using ESBuild, SASS for CSS, and Mithril as the web framework).
- `lib/` holds shared library code.

All new files you create should have `from iafisher_foundation.prelude import *`.

The `prelude` re-exports some common symbols, including `List`, `Dict`, and `Optional` from
`typing`, `dataclass`, and modules such as `datetime`, `os`, `pathlib`, and `re` (this list
is not exhaustive).

The order of imports is:

```
<python standard library imports>

<third-party library imports>

from app.foo import bar
from iafisher_foundation import foo
from iafisher_foundation.prelude import *
from lib.foo import bar
```

Imports should be alphabetized within each section, and `import foo` should come before `from foo import bar`.

Common libraries:

- Use `lib/command` to define command-line interfaces, not `argparse`.
- Use `timehelper.now()` from `iafisher_foundation.timehelper` to get the current time as an aware datetime for the
  local timezone.
- Use `LOG` from the prelude for logging.
- Use `iafisher_foundation.tabular` to print output in a tabular format.
- Use `lib/simplemail` or `lib/emailalerts` to send emails.
- Use `lib/pdb` to interact with the Postgres database.
- Use `lib/kgjson` to define dataclasses that can be serialized to and from JSON.
- Use `lib/webserver` to write web apps.
- Use `lib/githelper` to work with Git.

`iafisher_foundation` is a separate repository whose source code you don't have access to.

Search for examples in the repo if you are unsure how to use a library.

The current Python version is Python 3.11. The code you write may run on both a macOS laptop and a
Linux server.

### Deployment context
The programs in this repository are used exclusively by me, the software developer. Some of them run on my laptop and some of them are deployed to a Linux server. The Linux server is connected to my laptop and phone via a Tailscale VPN.

You can assume that the user is trusted and that the code runs in a trusted environment. Authentication is not necessarily for web applications since they are not accessible to the public internet.

### Additional conventions
- Code is formatted with Black-style conventions (line length 88). Flake8 and mypy run over the repo, with `disallow_untyped_calls = True`, so add type hints to new functions and public APIs.
- Prefer raising `KgError` (from the prelude) for user-facing errors, with helpful `key=value` context; let CLI wrappers print the resulting message instead of calling `sys.exit` from libraries.
- Use `LOG` (from the prelude) for logging; do not reconfigure logging by hand. `lib/kglogging` initializes logging for command-line tools.
- Prefer `@dataclass` for structured data. For JSON-on-disk config or state, subclass `lib.kgjson.Base` and use its `serialize`/`deserialize`/`load`/`save`/`with_lock` helpers.
- For Postgres, use `lib.pdb.connect()` and its `Connection` helpers (`fetch_one`, `fetch_all`, `fetch_val`, `execute_many_and_fetch_all`) plus generated `*models.py` files instead of ad-hoc SQL when possible.
- For command-line tools, put entrypoints under `app/`, use `lib/command` and call `command.dispatch(...)` in the `if __name__ == "__main__"` guard.
- For web apps, use `lib/webserver` (`make_app`, `make_template`, `make_command`) on top of Flask. Keep HTTP handlers thin and put business logic in `lib/` or app-specific modules.
- For filesystem and OS operations, prefer `lib/oshelper` (e.g., `replace_file`, `LockFile`) and `lib/kgenv` (paths, machine/env selection) over ad-hoc code.
- For human-facing durations, sizes, and times, use `lib/humanunits` (e.g., `parse_duration`, `parse_bytes`, `parse_time`) and `iafisher_foundation.timehelper` (`now()`, `today()`, `TZ_NYC`, `TZ_UTC`) instead of manual parsing/formatting.
- For tests, put tests next to the code (typically `tests.py`) and extend `lib.testing.Base` or `BaseWithDatabase`; use helpers like `assertStdout` and `expunge_datetimes` for stable output. New tests should use `expecttest` when appropriate.

### Code style
- Do not write any comments.
- Do not create any Markdown files unless explicitly instructed to.
