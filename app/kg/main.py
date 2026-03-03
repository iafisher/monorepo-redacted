import code
import importlib
import readline
import subprocess
import sys
import time
from typing import Annotated

from app.jobserver.cli import cmd as jobserver_cmd
from lib import command, fzf, humanunits, kgenv, simplemail
from iafisher_foundation import colors
from iafisher_foundation.prelude import *


def main_check_heartbeat(
    *,
    max_age: Annotated[
        datetime.timedelta, command.Extra(converter=humanunits.parse_duration)
    ],
) -> None:
    max_age_secs = max_age.total_seconds()
    heartbeat_dirpath = kgenv.get_ian_dir() / "logs" / "heartbeat"
    heartbeat_filepath = heartbeat_dirpath / "heartbeat.empty"
    statbuf = heartbeat_filepath.stat()

    secs_since_epoch = time.time()
    age_secs = secs_since_epoch - statbuf.st_mtime
    LOG.info(
        f"age={age_secs:.1f}s ({secs_since_epoch:.1f} - {statbuf.st_mtime:.1f}), "
        + f"max_age={max_age_secs:.1f}s"
    )
    if age_secs > max_age_secs:
        LOG.info("FAIL")

        fail_file = heartbeat_dirpath / "heartbeat_failed_email_already_sent"
        if fail_file.exists():
            LOG.info("%s exists, not sending email", fail_file)
            # TODO(2026-02): Once the jobserver has a proper RPC interface, use that instead.
            proc = subprocess.run(["kg", "jobs", "daemon", "status"])
            if proc.returncode == 0:
                LOG.info("daemon appears to be running, deleting %s", fail_file)
                fail_file.unlink()
        else:
            machine_fallback = "<unknown>"
            try:
                machine = kgenv.get_machine_opt()
                if machine is None:
                    machine = kgenv.get_env().get("KG_MACHINE", machine_fallback)
            except Exception:
                LOG.exception("failed to get machine name")
                machine = machine_fallback

            minutes = max_age_secs / 60
            simplemail.send_email(
                f"Jobserver heartbeat missed on {machine}",
                f"<p>The heartbeat file on {machine} has not been touched in {minutes:.1f} minutes. "
                + "This may indicate that the jobserver is not running properly.</p> "
                + f"<p>Once the problem has been fixed, delete <code>{fail_file}</code> on {machine}.</p>",
                recipients=["ian@iafisher.com"],
                html=True,
            )
            fail_file.touch()

        sys.exit(1)
    else:
        LOG.info("OK")


def main_logs(app: Optional[str], *, follow: bool = False) -> None:
    logs_dir = kgenv.get_ian_dir() / "logs"
    if app is None:
        app = fzf.select(
            [p.name for p in logs_dir.iterdir() if p.is_dir()], sorted=True
        )

    d = logs_dir / app
    if not d.exists():
        raise KgError("directory does not exist", directory=d)

    possibilities = list(d.glob("**/*.log"))
    if len(possibilities) == 0:
        raise KgError("no log files found", directory=d)

    choice = fzf.select(
        [str(p.relative_to(d)) for p in possibilities],
        preview="tail %s/{}" % d,
        preview_wrap=True,
        sorted=True,
    )
    path = d / choice
    if follow:
        subprocess.run(["tail", "-n", "50", "-f", path])
    else:
        subprocess.run(["less", "-F", path])


def main_shell() -> None:
    os.chdir(kgenv.get_code_dir())

    local: Dict[str, Any] = {}
    imported: List[str] = []
    for module_path in pathlib.Path("lib").iterdir():
        if not module_path.is_dir():
            continue

        name = module_path.name
        module = importlib.import_module(f"lib.{name}")
        if name == "prelude":
            for key in dir(module):
                if key.startswith("_"):
                    continue

                local[key] = getattr(module, key)
        else:
            imported.append(name)
            local[name] = module

    imported.sort()
    for module_name in imported:
        print(f"{colors.cyan('from')} lib {colors.cyan('import')} {module_name}")
    print(f"{colors.cyan('from')} lib.prelude {colors.cyan('import')} *")
    print()

    histfile = kgenv.get_ian_dir() / ".shellhistory"
    if histfile.exists():
        readline.read_history_file(histfile)
    code.interact(local=local)
    readline.write_history_file(histfile)


cmd = command.Group(help="Umbrella command for Khaganate services.")
cmd.add2(
    "check-heartbeat",
    main_check_heartbeat,
    help="Check the heartbeat file.",
    less_logging=False,
)
cmd.add("jobs", jobserver_cmd)
cmd.add2("logs", main_logs, help="Print logs for apps.")
cmd.add2("shell", main_shell)

if __name__ == "__main__":
    command.dispatch(cmd)
