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
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="bookmarks")) > 0
        )
