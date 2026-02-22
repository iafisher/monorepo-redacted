from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="simplemail"),
            """\
Usage: simplemail ...

  Send an email.

Arguments:

  -body ARG
  -recipient ARGS..
  -subject ARG
""",
        )
