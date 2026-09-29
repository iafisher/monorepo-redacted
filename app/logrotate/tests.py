from iafisher.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="logrotate")) > 0
        )
