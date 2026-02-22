from app.llmweb.webserver import cmd
from iafisher_foundation.prelude import *  # noqa: F401
from lib import command

if __name__ == "__main__":
    command.dispatch(cmd)
