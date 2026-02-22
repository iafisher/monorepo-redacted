from iafisher_foundation.prelude import *
from lib.testing import *

from .dblog import _get_app_or_lib


class Test(Base):
    def test_get_app_or_lib(self):
        self.assertEqual(
            ("app", "llm"), _get_app_or_lib("~/Code/monorepo/app/llm/main.py")
        )
        self.assertEqual(
            ("lib", "colors"), _get_app_or_lib("~/Code/monorepo/lib/colors/colors.py")
        )
        self.assertEqual(None, _get_app_or_lib("~/Code/monorepo/demo.py"))
