from iafisher.prelude import *
from lib import command


def main_run() -> None:
    todo()


def main_run_all() -> None:
    todo()


cmd = command.Group(help="Run and manage background jobs.")
cmd.add2("run", main_run, help="Run one job by name.")
cmd.add2("run-all", main_run_all, help="Run all jobs that are ready to run.")

if __name__ == "__main__":
    command.dispatch(cmd)
