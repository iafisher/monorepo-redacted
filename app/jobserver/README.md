The jobserver runs jobs. It has a daemon process that is registered under Launchd (macOS) or Systemd (Linux), and a client program (`kg jobs`) that can query state, enqueue jobs, etc.

Jobs are defined in `jobserver.json` files in the monorepo. The deployment process automatically discovers these files and uploads them.

Example:

```json
{
  "jobs": [
    {
      "name": "testjob",
      "cmd": ["date"],
      "machines": ["laptop"]
    },
  ]
}
```

Supported keys for jobs:

- `name`: e.g., `iafisher::nightly_upload` (underscores, not dashes)
- `cmd`: the command to run, as an array of strings
    - supports the special signifiers `[[date]]`, `[[yesterday]]`, and `[[lastmonth]]` (which resolves to the first day of the previous month)
- `machines`: the machines the job should run on (currently can include `laptop` and `homeserver`)
- `schedule`: e.g., `{"hourly": {"interval_mins": 30}}` or `{"daily": {"times_of_day": ["11pm"]}}`
- `extra_path`: extra entries to add to the `PATH` environment variable (child jobs run with a limited set of directories on the `PATH`)
- `extra_pythonpath`: extra entries to add to the `PYTHONPATH` environment variable (this usually is not necessary)
- `working_directory`: run the job in this directory (defaults to `~/.ian/logs/<job>`)

## Internals
The daemon process loops forever, checking for work to do and then going to sleep briefly. It reads from a state file on disk to decide what to do next. After a job finishes, it writes to the state file.

The daemon takes two file locks:

- The PID lockfile, for the duration the process is running
- The `state.lock` file, briefly while it is updating the state (there's no good reason to have a separate lockfile versus just locking `state.json` itself)

The client program does not directly communicate with the daemon at all; it just reads from the same state file.

`SIGHUP` causes the daemon process to exit gracefully, i.e., the next time the main loop runs. `SIGTERM` causes the daemon process to exit abruptly. In either case, the daemon is configured in Launchd/Systemd to automatically restart.

To run child jobs, the jobserver uses the traditional `fork` + `exec` method.

The jobserver sends an email when it boots up, to help detect crashes. On each machine, there is a heartbeat job that runs every 5 minutes and calls `touch ~/.ian/logs/heartbeat/heartbeat.empty`. Separately, a cron job (outside of the jobserver entirely) checks the age of the heartbeat file and sends an email if it is too old. This helps detect when the jobserver is down completely. The cron job is defined as:

```
*/15 * * * * $HOME/.ian/repos/current/bin/kg check-heartbeat -max-age 30m >> $HOME/.ian/logs/heartbeat/cron.log 2>&1
```

### Scheduling
Four types of schedules are supported:

- hourly: run every X minutes
- daily: run once (or twice, etc.) a day at a fixed time
- weekly: run on certain days of the week
- monthly: run on certain days of the month

The implementation of each schedule has a `get_next_scheduled_time(now)` function which returns the next time, `>= now`, that the scheduled job should be run.

The jobserver keeps track of the next scheduled time for each job in its persistent state. On start-up, if any job has a blank `next_scheduled_time`, it is filled by calling the function for the job's schedule. Each time the jobserver wakes up, it checks for each job if it is now later than the scheduled time. If it is, it starts the job, and sets the next scheduled time by calling the function (potentially before the job has finished).

Edge cases to consider:

- A job overruns its time slot. Example: The job runs every 5 minutes. The 1pm run takes 12 minutes. At 1pm, the jobserver would have set the next scheduled time to 1:05. At 1:12, the jobserver again considers whether to run the job (it will not start a job when a previous run has not finished). Because the next scheduled run is at 1:05, the job will be immediately run and the next scheduled time will be set to 1:15 (_not_ 1:10).
- The jobserver misses a job's scheduled time because it is not running. (The jobserver wakes up infrequently when my laptop is in sleep mode.) This is effectively equivalent to the example above: imagine that the jobserver crashed at 1pm and restarted at 1:12.
- A job is configured to run on the 31st of every month. What happens for months that have fewer than 31 days? Or worse, what happens in February if a job is supposed to run on the 29th, 30th, and 31st? This implementation will run the job once on the last day of the month in either case, which seems like the only correct thing to do.
- What happens to a daily job that is supposed to run during the daylight saving time transition? It should run only once, regardless of whether a naive implementation would cause it to run twice (falling back) or never (springing forward). How does this work in practice?
  - Falling back: At 00:00 on transition day, job is scheduled for 1:30am. At 1:30am DT the job runs and the next scheduled time is set to be 1:30am the next day. When 1:30am ST occurs, the job does not run.
  - Springing forward: At 00:00 on transition day, job is scheduled for 2:30am. The clock skips from 1:59am to 3am and the job is run. This results in the job running, depending on your perspective, either 30 minutes late (by wall-clock time) or 30 minutes early (by real time).
- The user manually runs the job. Does it skip its next slot? I think the user should be able to choose whether this happens or not. Currently, the next slot will _not_ be skipped, but I think implementing is as easy as adding a `skip_next_run` flag to the state. (What happens if the user manually runs the job when `skip_next_run` is already set? Does it skip the next next run?)
