from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="emailalerts"),
            """\
Usage: emailalerts SUBCMD

Subcommands:

  clear        . Clear throttled alerts without sending them.
  flush        . Flush throttled email alerts.
  list         . List email alerts that are currently throttled.
  send-test    . Send a test alert.


------------

Usage: emailalerts clear ...

  Clear throttled alerts without sending them.

Arguments:

  label


------------

Usage: emailalerts flush ...

  Flush throttled email alerts.

Arguments:

 [-force]    . send messages even if they would still be throttled


------------

Usage: emailalerts list ...

  List email alerts that are currently throttled.


------------

Usage: emailalerts send-test ...

  Send a test alert.
""",
        )
