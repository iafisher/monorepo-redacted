from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="golinks"),
            """\
Usage: golinks SUBCMD

  Manage go links.

Subcommands:

  add
  delete
  list
  serve
  update


------------

Usage: golinks add ...

Arguments:

  -name ARG
  -url ARG


------------

Usage: golinks delete ...

Arguments:

  name


------------

Usage: golinks list ...

Arguments:

 [-show-deprecated]    . show deprecated golinks that are no longer active


------------

Usage: golinks serve ...

Arguments:

  -port ARG


------------

Usage: golinks update ...

Arguments:

  name
  -to ARG
""",
        )
