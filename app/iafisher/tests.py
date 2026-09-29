import os
import subprocess

from app.iafisher.main import CODE_PATH, cmd
from app.iafisher.mdpages import hackily_insert_property
from lib import command
from lib.testing import *


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

    def test_hackily_insert_property(self):
        self.assertExpectedInline(
            hackily_insert_property("Hello, world!\n", "test-key", "test-value"),
            """\
---
test-key: test-value
---

Hello, world!
""",
        )

        self.assertExpectedInline(
            hackily_insert_property(
                "\n\n---\nexisting-key: existing-value\n---\nHello, world!\n",
                "test-key",
                "test-value",
            ),
            """\


---
existing-key: existing-value
test-key: test-value
---
Hello, world!
""",
        )

    def test_help_text(self):
        self.assertTrue(
            len(command.get_help_text_recursive(cmd, program="iafisher")) > 0
        )
