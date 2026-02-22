import os
import subprocess

from app.iafisher.main import CODE_PATH
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_live_server(self):
        # This test is a little convoluted: we shell out to a Django test command in another repo,
        # which in turn shells out back to the `iafisher` command in this repo.
        #
        # Why not move the test entirely to this repo? Because we wouldn't be able to use Django's
        # `LiveServerTestCase` class, which handles initializing a clean database for us.
        old_cwd = os.getcwd()
        try:
            os.chdir(CODE_PATH)
            subprocess.run(
                [".venv/bin/python3", "manage.py", "test", "blog", "mdpages"],
                check=True,
            )
        finally:
            os.chdir(old_cwd)

    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="iafisher"),
            """\
Usage: iafisher SUBCMD

  Management commands for iafisher.com

Subcommands:

  blog            . Helper commands for my personal blog.
  deploy          . Deploy a new version of the server.
  django          . Run Django's manage.py script on the prod server.
  list-deploys
  local           . Helper commands for local development.
  mdpages         . Helper commands for Markdown pages.
  provision       . Provision a new server from scratch.
  psql            . Launch a psql shell connected to the prod database.
  rollback        . Roll back to a previous deployment.
  stats           . Update the site stats page.


------------

Usage: iafisher deploy ...

  Deploy a new version of the server.


------------

Usage: iafisher django ...

  Run Django's manage.py script on the prod server.


------------

Usage: iafisher provision ...

  Provision a new server from scratch.

Arguments:

  ip_addr


------------

Usage: iafisher psql ...

  Launch a psql shell connected to the prod database.


------------

Usage: iafisher blog SUBCMD

  Helper commands for my personal blog.

Subcommands:

  mail      . Send the newsletter for a new blog post.
  upload    . Upload a new blog post.


------------

Usage: iafisher blog mail ...

  Send the newsletter for a new blog post.

Arguments:

  -url ARG                 . URL of blog post
  [-allow-resend]          . allow the re-sending of a campaign that has already been sent
  [-test-recipient ARG]    . send to a single test recipient instead of the mailing list (default: None)


------------

Usage: iafisher blog upload ...

  Upload a new blog post.

Arguments:

 [-api-key ARG]      . use this API key instead of reading from secrets file (default: None)
 [-local]            . upload to a locally-running server
 [-local-url ARG]    . URL for local upload (only valid if -local also passed) (default: None)
 [-no-confirm]       . don't require confirmation
 [-path ARG]         . path to blog post; if not supplied, will search for ready-to-publish posts (default: None)


------------

Usage: iafisher mdpages SUBCMD

  Helper commands for Markdown pages.

Subcommands:

  upload    . Upload a Markdown page.


------------

Usage: iafisher mdpages upload ...

  Upload a Markdown page.

Arguments:

 [-all]              . upload all pages, even if unchanged
 [-api-key ARG]      . use this API key instead of reading from secrets file (default: None)
 [-dir ARG]          . directory of Markdown pages (default: ~/Obsidian/personal-site)
 [-local]            . upload to a locally-running server
 [-local-url ARG]    . URL for local upload (only valid if -local also passed) (default: None)
 [-verbose]


------------

Usage: iafisher list-deploys ...


------------

Usage: iafisher local SUBCMD

  Helper commands for local development.

Subcommands:

  runserver    . Run the development server.


------------

Usage: iafisher local runserver ...

  Run the development server.

Arguments:

 [-p ARG]    . (default: 8888)


------------

Usage: iafisher rollback ...

  Roll back to a previous deployment.

Arguments:

  old_deploy


------------

Usage: iafisher stats ...

  Update the site stats page.

Arguments:

 [-dry-run]
""",
        )
