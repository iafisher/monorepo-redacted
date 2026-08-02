from app.kiosk.webserver import cmd
from iafisher.prelude import *  # noqa: F401
from lib import command

if __name__ == "__main__":
    command.dispatch(cmd)
