import os
import tempfile
from lib.testing import *

from .emailalerts import send_alert


class Test(Base):
    def test_throttling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # TODO(2025-02): better way of doing this (e.g., global `KGDIR` environment variable)
            os.environ["KG_EMAILALERTS_STATE_FILE"] = os.path.join(tmpdir, "state.json")
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
