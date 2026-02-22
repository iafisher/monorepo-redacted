from app.wikipedia.tidy import cmd as tidy_cmd
from app.wikipedia.webserver import cmd as webserver_cmd
from iafisher_foundation.prelude import *  # noqa: F401
from lib import command

cmd = command.Group()
cmd.add("serve", webserver_cmd)
cmd.add("tidy", tidy_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
