JOBSERVER_CRASHED = """\
<p>
  The jobserver crashed on the machine '%(machine)s' because of a Python exception.
</p>

<pre><code>%(tb)s</code></pre>
"""

JOBSERVER_SPAWN_EXCEPTION = """\
<p>
  The jobserver encountered an error while running job %(job)s on the machine '%(machine)s'.
  Depending on when the exception occurred, the job may or may not have been started.
</p>

<pre><code>%(tb)s</code></pre>
"""

JOB_FAILED = """\
<p>A job scheduled to run exited with a non-zero status.</p>

<table>
<tbody>
<tr><td>Job name:</td><td>%(job_name)s</td></tr>
<tr><td>Machine:</td><td>%(machine)s</td></tr>
<tr><td>Exit status:</td><td>%(status)s</td></tr>
<tr><td>Time:</td><td>%(time)s</td></tr>
<tr><td>Log file:</td><td>%(logfile)s</td></tr>
</tbody>
</table>

<h2>End of log</h2>
<pre><code>%(logtail)s</code></pre>
"""

# TODO(2025-06): Maybe set width/height to 100% on the whole body
JOB_FAILED_EXTRA_CSS = """\
body {
  padding-bottom: 20px;
}

table {
  /* On mobile, table gets truncated at end otherwise. */
  margin-bottom: 50px;
}

tr td:first-child {
  padding-right: 10px;
  font-weight: bold;
}

td {
  padding-bottom: 5px;
}
"""
