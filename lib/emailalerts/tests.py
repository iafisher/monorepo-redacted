import os
import pathlib
import tempfile

from lib.testing import *

from .emailalerts import send_alert


class Test(Base):
    def test_throttling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["KG_TEST_DIR"] = tmpdir
            appdir = pathlib.Path(tmpdir) / "apps" / "emailalerts"
            appdir.mkdir(parents=True)

            f = lambda: send_alert(
                "test email",
                "test body",
                html=False,
                throttle_label=["test"],
            )
            self.assertStdout(
                "EMAIL: To: inbox@iafisher.com, Subject: [kg] Alert: test email\n", f
            )
            # should be throttled the second time
            self.assertStdout("", f)
