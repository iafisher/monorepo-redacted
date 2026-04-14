from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .webserver import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="llmweb"),
            """\
Usage: llmweb ...

  Run the webserver.

Arguments:

 [-debug]       . Run the server in debug mode.
 [-port ARG]    . (default: 7600)
""",
        )
