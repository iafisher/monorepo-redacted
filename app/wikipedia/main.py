from app.wikipedia.llmapedia.export import main as main_llmapedia_export
from app.wikipedia.tidy import cmd as tidy_cmd
from app.wikipedia.webserver import cmd as webserver_cmd
from iafisher_foundation.prelude import *  # noqa: F401
from lib import command

cmd = command.Group()
llmapedia_cmd = command.Group()
llmapedia_cmd.add2("export", main_llmapedia_export, less_logging=False)
cmd.add("llmapedia", llmapedia_cmd)
cmd.add("serve", webserver_cmd)
cmd.add("tidy", tidy_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
