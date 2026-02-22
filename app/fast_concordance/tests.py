from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="fast-concordance"),
            """\
Usage: fast-concordance SUBCMD

  Umbrella command for fast-concordance

Subcommands:

  deploy              . Deploy the server.
  deploy-benchmark    . Deploy the benchmark binary.
  load-test           . Load-test the server.
  logs                . Display server logs.
  status              . Display server status.


------------

Usage: fast-concordance deploy ...

  Deploy the server.

Arguments:

  directory            . directory containing the fast-concordance files
  [-include-ebooks]    . deploy the (processed) ebook files
  [-skip-build]        . skip building the server


------------

Usage: fast-concordance deploy-benchmark ...

  Deploy the benchmark binary.

Arguments:

  directory    . directory containing the fast-concordance files


------------

Usage: fast-concordance load-test ...

  Load-test the server.

Arguments:

 [-base-url ARG]    . (default: 'https://iafisher.com')
 [-gap ARG]         . wait this long between requests (default: None)
 [-keyword ARG]     . (default: 'vampire')
 [-n ARG]           . how many simultaneous requests to make (default: 1)
 [-trials ARG]      . repeat this many times (default: 1)


------------

Usage: fast-concordance logs ...

  Display server logs.


------------

Usage: fast-concordance status ...

  Display server status.
""",
        )
