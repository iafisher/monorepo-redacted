from typing import Literal

from iafisher_foundation.prelude import *


MACHINE_HOMESERVER = "homeserver"
MACHINE_LAPTOP = "laptop"

Mode = Literal["prod", "dev", "test"]


def get_mode() -> Mode:
    mode_str = os.environ.get("KG_MODE")
    if mode_str is None:
        return "dev"
    elif mode_str == "prod":
        return "prod"
    elif mode_str == "test":
        return "test"
    else:
        raise KgError("invalid KG_MODE", mode_str=mode_str)


def get_app_name() -> str:
    p = pathlib.Path(sys.argv[0]).absolute()
    for i in reversed(range(1, len(p.parts))):
        if p.parts[i - 1] == "app":
            return p.parts[i]

    raise KgError("could not find app name from path", path=p)


ENV_CODE_DIR = "KG_CODE_DIR"


def get_code_dir() -> pathlib.Path:
    p = get_code_dir_opt()
    if p is None:
        raise KgError("could not get code directory", envvar=ENV_CODE_DIR)
    return p


def get_ian_dir() -> pathlib.Path:
    match get_mode():
        case "prod":
            return pathlib.Path.home() / ".ian"
        case "dev":
            return pathlib.Path.home() / ".ian" / "dev"
        case "test":
            return pathlib.Path(os.environ["KG_TEST_DIR"])


def get_app_dir(appname: str) -> pathlib.Path:
    return get_ian_dir() / "apps" / appname


def get_code_dir_opt() -> Optional[pathlib.Path]:
    p = os.environ.get(ENV_CODE_DIR)
    return pathlib.Path(p) if p is not None else None


_kg_machine_envvar = "KG_MACHINE"


def get_machine() -> str:
    r = get_machine_opt()
    if r is None:
        raise KgError(
            f"{_kg_machine_envvar} environment variable is not set on this machine."
        )
    return r


def get_machine_opt() -> Optional[str]:
    return os.environ.get(_kg_machine_envvar)


def get_env() -> Dict[str, str]:
    env_file = get_ian_dir() / "env"
    if not env_file.exists():
        return {}

    r: Dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        key, value = line.split("=", maxsplit=1)
        # TODO(2026-02): Handle quoted strings.
        r[key] = value

    return r
