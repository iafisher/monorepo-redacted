import m from "mithril";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import { formatBytes } from "../common/utils";
import * as api from "./api";
import * as rpc from "./rpc";

function formatDateTime(dt: string | null): string {
  if (!dt) return "never";
  return new Date(dt).toLocaleString();
}

class JobRunRowView {
  view(vnode: m.Vnode<{ run: rpc.JobRunItem; jobName: string }>) {
    const run = vnode.attrs.run;
    const jobName = vnode.attrs.jobName;
    const statusClass =
      run.exitStatus === null
        ? "status-none"
        : run.exitStatus === 0
          ? "status-success"
          : "status-failure";

    return m("tr", [
      m("td", formatDateTime(run.timeRun)),
      m(
        "td",
        { class: statusClass },
        run.exitStatus === null ? "-" : run.exitStatus.toString(),
      ),
      m(
        "td",
        run.wallTimeSecs !== null ? `${run.wallTimeSecs.toFixed(1)}s` : "-",
      ),
      m(
        "td",
        run.userTimeSecs !== null ? `${run.userTimeSecs.toFixed(1)}s` : "-",
      ),
      m(
        "td",
        run.systemTimeSecs !== null ? `${run.systemTimeSecs.toFixed(1)}s` : "-",
      ),
      m("td", run.maxMemory !== null ? formatBytes(run.maxMemory) : "-"),
      m(
        "td",
        run.logAvailable
          ? m("a", { href: `/log/${jobName}/${run.logTimestamp}` }, "view log")
          : "-",
      ),
    ]);
  }
}

class JobDetailPage {
  private jobName: string;
  private job: rpc.JobDetailResponse | null;
  private controller: Controller;

  constructor(vnode: m.Vnode<{ jobName: string }>) {
    this.jobName = vnode.attrs.jobName;
    this.job = null;
    this.controller = new Controller();
  }

  async oninit(vnode: m.Vnode<{ jobName: string }>) {
    this.jobName = vnode.attrs.jobName;
    try {
      this.job = await api.fetchJobDetail(this.jobName);
    } catch (e) {
      this.controller.pushError(`failed to load job: ${e}`);
      return;
    }
    m.redraw();
  }

  view() {
    if (!this.job) {
      return m(".page-container", [
        m(HeaderView, {
          controller: this.controller,
          title: "Job",
          links: [{ text: "← Back", href: "/" }],
        }),
        m(".loading", "Loading..."),
      ]);
    }

    return m(".page-container", [
      m(HeaderView, {
        controller: this.controller,
        title: this.job.name,
        links: [{ text: "← back", href: "/" }],
      }),
      m(".job-detail", [
        m(".job-config", [
          m("h2", "Configuration"),
          m("table.config-table", [
            m("tr", [m("td", "Command:"), m("td", this.job.cmd.join(" "))]),
            m("tr", [
              m("td", "Enabled:"),
              m("td", this.job.enabled ? "yes" : "no"),
            ]),
            m("tr", [
              m("td", "Schedule:"),
              m("td", this.job.schedule || "none"),
            ]),
            m("tr", [m("td", "Date Added:"), m("td", this.job.dateAdded)]),
            m("tr", [
              m("td", "Last Run:"),
              m("td", formatDateTime(this.job.lastRunTime)),
            ]),
            m("tr", [
              m("td", "Next Run:"),
              m("td", formatDateTime(this.job.nextScheduledTime)),
            ]),
            this.job.workingDirectory
              ? m("tr", [
                  m("td", "Working Directory:"),
                  m("td", this.job.workingDirectory),
                ])
              : null,
            this.job.alertHighPriority
              ? m("tr", [m("td", "Alert Priority:"), m("td", "high")])
              : null,
          ]),
        ]),
        m(".job-runs", [
          m("h2", "Recent Runs"),
          m("table.runs-table", [
            m("thead", [
              m("tr", [
                m("th", "Time"),
                m("th", "Exit Status"),
                m("th", "Wall Time"),
                m("th", "User Time"),
                m("th", "System Time"),
                m("th", "Max Memory"),
                m("th", "Log"),
              ]),
            ]),
            m(
              "tbody",
              this.job.runs.map((run) =>
                m(JobRunRowView, { run, jobName: this.job!.name }),
              ),
            ),
          ]),
        ]),
      ]),
    ]);
  }
}

export default JobDetailPage;
