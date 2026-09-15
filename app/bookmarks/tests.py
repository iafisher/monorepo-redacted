from app.bookmarks.import_from_zulip import extract_author
from iafisher.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_zulip_extract_author(self):
        content = '<p><span class="user-mention" data-user-id="717064">@John Doe (he) (S1\'24)</span> has a new blog post: <a href="https://blaggregator.herokuapp.com/post/Hkfu3A/view">\u4e09\u5341\u516b</a></p>'
        self.assertEqual("John Doe", extract_author(dict(content=content)))

    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="bookmarks"),
            """\
Usage: bookmarks SUBCMD

  Manage bookmarks database.

Subcommands:

  import    . Import bookmarks from other sources.
  prune     . Prune bookmarks that have not been read after a certain time
  serve     . Run the webserver.


------------

Usage: bookmarks import SUBCMD

  Import bookmarks from other sources.

Subcommands:

  chrome    . Import unread bookmarks from Chrome.
  hn        . Import bookmarks from the Hacker News front page
  rss       . Import bookmarks from RSS feeds
  test      . Import test data.
  zulip     . Import bookmarks from the Recurse Center Zulip instance


------------

Usage: bookmarks import chrome ...

  Import unread bookmarks from Chrome.

Arguments:

 [-delete-existing]    . delete any existing Chrome unread bookmarks from the database
 [-dry-run]


------------

Usage: bookmarks import hn ...

  Import bookmarks from the Hacker News front page

Arguments:

 [-comment-limit ARG]    . limit the number of comments to query per story (default: 10)
 [-model ARG]            . LLM model to use (default: 'any_fast')
 [-story-limit ARG]      . limit the number of stories to query (default: 20)


------------

Usage: bookmarks import rss ...

  Import bookmarks from RSS feeds

Arguments:

 [-dry-run]


------------

Usage: bookmarks import test ...

  Import test data.

Arguments:

 [-delete-existing]    . delete any existing bookmarks from the database


------------

Usage: bookmarks import zulip ...

  Import bookmarks from the Recurse Center Zulip instance

Arguments:

 [-dry-run]


------------

Usage: bookmarks prune ...

  Prune bookmarks that have not been read after a certain time

Arguments:

  -days-to-retain ARG
  [-dry-run]


------------

Usage: bookmarks serve ...

  Run the webserver.

Arguments:

 [-debug]       . Run the server in debug mode.
 [-port ARG]    . (default: 5000)
""",
        )
