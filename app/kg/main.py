import code
import importlib
import readline
import shlex
import subprocess
import sys
import time

from app.jobserver.cli import cmd as jobserver_cmd
from iafisher import colors, timehelper
from iafisher.prelude import *
from iafisher.scripting import sh0
from lib import command, fzf, humanunits, kgenv, simplemail


def main_check_heartbeat(
    *,
    max_age: Annotated[
        dt.timedelta, command.Extra(converter=humanunits.parse_duration)
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
            + "This may indicate that the jobserver is not running properly.</p>",
            recipients=["ian@iafisher.com"],
            html=True,
        )
        sys.exit(1)
    else:
        LOG.info("OK")


def main_email_after_reboot() -> None:
    now = timehelper.now()
    machine = opt_or(kgenv.get_machine_opt(), "unknown")
    simplemail.send_email(
        subject=f"kg: machine {machine} rebooted",
        body=f"This is an informational email that the machine {machine} has rebooted as of {now}."
        " No action is required.",
        recipients=[simplemail.HIGH_PRIORITY_RECIPIENT],
        html=False,
    )


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


def main_remote(args: Annotated[List[str], command.Extra(passthrough=True)]) -> None:
    kgenv.assert_on_laptop()
    sh0(shlex.join(["ssh", "homeserver2"] + args))


def main_shell() -> None:
    os.chdir(kgenv.get_code_dir())

    local: Dict[str, Any] = {}
    imported: List[str] = []
    for module_path in pathlib.Path("lib").iterdir():
        if not module_path.is_dir():
            continue

        name = module_path.name
        module = importlib.import_module(f"lib.{name}")
        imported.append(name)
        local[name] = module

    def _import_star(module_name: str) -> None:
        module = importlib.import_module(module_name)
        for key in dir(module):
            if key.startswith("_"):
                continue

            local[key] = getattr(module, key)

    foundation_module_name = "iafisher"
    _import_star(foundation_module_name)
    prelude_module_name = f"{foundation_module_name}.prelude"
    _import_star(prelude_module_name)

    imported.sort()
    for module_name in imported:
        print(f"{colors.cyan('from')} lib {colors.cyan('import')} {module_name}")
    print(f"{colors.cyan('from')} {foundation_module_name} {colors.cyan('import')} *")
    print(f"{colors.cyan('from')} {prelude_module_name} {colors.cyan('import')} *")
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
cmd.add2(
    "email-after-reboot",
    main_email_after_reboot,
    help="Send an email after rebooting.",
    less_logging=False,
)
cmd.add("jobs", jobserver_cmd)
cmd.add2("logs", main_logs, help="Print logs for apps.")
cmd.add2("r", main_remote, help="Run a command on the remote server.")
cmd.add2("shell", main_shell)

if __name__ == "__main__":
    command.dispatch(cmd)
