import os
import tempfile

from app.jobrunner import main
from iafisher.prelude import *
from lib.testing import *


class Tests(Base):
    def test_run_one_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            jobname = "testjob"
            log_message = "hello, world!"
            file_created_by_job = tmpdir / f"{jobname}.ran"
            toml_text = f"""\
[[jobs]]
name = "{jobname}"
cmd = ["bash", "-c", "echo '{log_message}' && touch {file_created_by_job}"]
"""
            self.set_up_tmpdir(tmpdir, toml_text)

            main.main_run(jobname)

            self.assertTrue(file_created_by_job.exists())
            log_files = list((tmpdir / "logs" / jobname).iterdir())
            self.assertEqual(len(log_files), 1, msg=repr(log_files))
            self.assertExpectedInline(
                log_files[0].read_text(),
                """\
hello, world!
""",
            )

    def set_up_tmpdir(self, tmpdir: pathlib.Path, toml_text: str) -> None:
        os.environ["KG_TEST_DIR"] = tmpdir.as_posix()
        os.environ["KG_CODE_DIR"] = tmpdir.as_posix()

        try:
            machine = os.environ["KG_MACHINE"]
        except KeyError:
            machine = "testmachine"
            os.environ["KG_MACHINE"] = machine

        (tmpdir / "machines" / machine).mkdir(parents=True)
        (tmpdir / "machines" / machine / "jobs.toml").write_text(toml_text)
