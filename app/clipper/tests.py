from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="clipper"),
            """\
Usage: clipper SUBCMD

  Clip webpages to send to my Kindle.

Subcommands:

  check     . Download, convert to EPUB, and check format.
  send      . Send a webpage directly to my Kindle.
  weekly    . Send a bundle of articles to my Kindle weekly.


------------

Usage: clipper check ...

  Download, convert to EPUB, and check format.

Arguments:

  url


------------

Usage: clipper send ...

  Send a webpage directly to my Kindle.

Arguments:

  url
  [-author ARG]    . (default: None)
  [-title ARG]     . (default: None)


------------

Usage: clipper weekly SUBCMD

  Send a bundle of articles to my Kindle weekly.

Subcommands:

  save    . Save a webpage to be sent to my Kindle.
  send    . Send the current weekly bundle to my Kindle.


------------

Usage: clipper weekly save ...

  Save a webpage to be sent to my Kindle.

Arguments:

  url


------------

Usage: clipper weekly send ...

  Send the current weekly bundle to my Kindle.
""",
        )
