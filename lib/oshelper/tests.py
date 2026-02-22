import os
import tempfile
from pathlib import Path

from lib.testing import *

from .oshelper import LockFile


class Test(Base):
    def test_lock_file(self):
        old_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                p = Path("test.lock")
                p.touch()
                with LockFile(p, exclusive=True):
                    lock2 = LockFile(p, exclusive=True)

                    with self.assertRaises(BlockingIOError):
                        lock2.acquire(wait=False)

                    # close the file
                    lock2.release()

                with LockFile(p, exclusive=False):
                    with LockFile(p, exclusive=False):
                        lock3 = LockFile(p, exclusive=True)

                        with self.assertRaises(BlockingIOError):
                            lock3.acquire(wait=False)

                        lock3.release()
        finally:
            os.chdir(old_cwd)
