from app.llmweb.templates import cmd as templates_cmd
from app.llmweb.webserver import cmd as webserver_cmd
from iafisher.prelude import *  # noqa: F401
from lib import command

cmd = command.Group()
cmd.add("serve", webserver_cmd)
cmd.add("templates", templates_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
