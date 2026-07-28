from iafisher.prelude import *
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
  send      . Send individual articles to my Kindle.
  weekly    . Send a weekly bundle of articles to my Kindle.


------------

Usage: clipper check ...

  Download, convert to EPUB, and check format.

Arguments:

  url


------------

Usage: clipper send SUBCMD

  Send individual articles to my Kindle.

Subcommands:

  file    . Send a file directly to my Kindle.
  url     . Send a webpage directly to my Kindle.


------------

Usage: clipper send file ...

  Send a file directly to my Kindle.

Arguments:

  filepath
  [-author ARG]
  [-title ARG]     . (default: None)


------------

Usage: clipper send url ...

  Send a webpage directly to my Kindle.

Arguments:

  url
  [-author ARG]    . (default: None)
  [-title ARG]     . (default: None)


------------

Usage: clipper weekly SUBCMD

  Send a weekly bundle of articles to my Kindle.

Subcommands:

  edit-state    . Manually edit the state file.
  list          . List webpages that would be sent.
  save          . Save a webpage to be sent to my Kindle.
  send          . Send the current weekly bundle to my Kindle.


------------

Usage: clipper weekly edit-state ...

  Manually edit the state file.


------------

Usage: clipper weekly list ...

  List webpages that would be sent.


------------

Usage: clipper weekly save ...

  Save a webpage to be sent to my Kindle.

Arguments:

  url


------------

Usage: clipper weekly send ...

  Send the current weekly bundle to my Kindle.

Arguments:

 [-do-not-clear]    . do not clear entries after sending (so subsequent sends will send the same URLs)
""",
        )
