from iafisher.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        # TODO(2026-08): This depends on the machine-specific setting of KG_DIR.
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="logrotate"),
            """\
Usage: logrotate ...

  Rotate logs.

Arguments:

  -max-age-days ARG    . delete log files older than this
  [-directory ARG]     . (default: ~/.ian/dev/logs)
  [-dry-run]
""",
        )
