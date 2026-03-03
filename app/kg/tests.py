from iafisher_foundation.prelude import *
from lib import command
from lib.testing import *

from .main import cmd


class Test(Base):
    def test_help_text(self):
        self.assertExpectedInline(
            command.get_help_text_recursive(cmd, program="kg"),
            """\
Usage: kg SUBCMD

  Umbrella command for Khaganate services.

Subcommands:

  check-heartbeat    . Check the heartbeat file.
  jobs               . Manage background jobs.
  logs               . Print logs for apps.
  shell


------------

Usage: kg check-heartbeat ...

  Check the heartbeat file.

Arguments:

  -max-age ARG


------------

Usage: kg jobs SUBCMD

  Manage background jobs.

Subcommands:

  daemon       . Manage the daemon.
  disable      . Disable a scheduled job.
  enable       . Enable a scheduled job that was previously disabled.
  history      . Show job history.
  launchctl    . Utilities for launchctl.
  list         . List background jobs.
  remove       . Remove a job from the schedule.
  run          . Manually run a job out of schedule.
  schedule     . Schedule a background job to run.
  show         . Show details about a job.
  webserver    . Run the webserver.


------------

Usage: kg jobs daemon SUBCMD

  Manage the daemon.

Subcommands:

  kill          . Kill the daemon.
  start         . Start the daemon.
  status        . Check the status of the daemon.
  test-crash    . Crash the daemon to test crash recovery.


------------

Usage: kg jobs daemon kill ...

  Kill the daemon.

  If the daemon is running under an OS service manager like launchd or
  systemd, it might immediately restart.

Arguments:

 [-sigkill]    . Send SIGKILL instead of SIGHUP.


------------

Usage: kg jobs daemon start ...

  Start the daemon.

Arguments:

 [-log-interval ARG]       . write a heartbeat log message this often (default: '5m')
 [-port ARG]               . (default: 6500)
 [-wakeup-interval ARG]    . wake up this often to check for jobs to run (default: '1s')


------------

Usage: kg jobs daemon status ...

  Check the status of the daemon.


------------

Usage: kg jobs daemon test-crash ...

  Crash the daemon to test crash recovery.


------------

Usage: kg jobs disable ...

  Disable a scheduled job.

Arguments:

  name


------------

Usage: kg jobs enable ...

  Enable a scheduled job that was previously disabled.

Arguments:

  name


------------

Usage: kg jobs history ...

  Show job history.

Arguments:

  name
  [-limit ARG]    . pass -1 to show all previous runs (default: 5)


------------

Usage: kg jobs launchctl SUBCMD

  Utilities for launchctl.

Subcommands:

  load       . Load the launchctl job.
  restart    . Unload and then load the launchctl job.
  unload     . Unload the launchctl job.


------------

Usage: kg jobs launchctl load ...

  Load the launchctl job.


------------

Usage: kg jobs launchctl restart ...

  Unload and then load the launchctl job.


------------

Usage: kg jobs launchctl unload ...

  Unload the launchctl job.


------------

Usage: kg jobs list ...

  List background jobs.

Arguments:

 [-disabled]    . Show disabled jobs.
 [-verbose]


------------

Usage: kg jobs remove ...

  Remove a job from the schedule.

Arguments:

  name


------------

Usage: kg jobs run ...

  Manually run a job out of schedule.

Arguments:

  name
  [-debug-env]    . Print the subprocess's environment variables.


------------

Usage: kg jobs schedule ...

  Schedule a background job to run.

Arguments:

  config_file              . config file (JSON)
  [-replace]               . Replace an existing scheduled job.
  [-skip-existing]         . Ignore existing jobs.
  [-skip-wrong-machine]    . Skip jobs set for a different machine, instead of failing.


------------

Usage: kg jobs show ...

  Show details about a job.

Arguments:

  name


------------

Usage: kg jobs webserver ...

  Run the webserver.

Arguments:

 [-debug]       . Run the server in debug mode.
 [-port ARG]    . (default: 7900)
 [-testdb]      . Run against the test database.


------------

Usage: kg logs ...

  Print logs for apps.

Arguments:

  app
  [-follow]


------------

Usage: kg shell ...
""",
        )
