from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="is-it-up"),
            """\
Usage: is-it-up ...

  Check if a website is online.

Arguments:

  url
  [-keyphrase ARG]    . also check that this keyphrase appears in the HTTP response (default: None)
""",
        )
