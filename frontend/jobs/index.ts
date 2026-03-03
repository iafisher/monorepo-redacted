import m from "mithril";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import * as api from "./api";
import * as rpc from "./rpc";

function formatDateTime(dt: string | null): string {
  if (!dt) return "never";
  const date = new Date(dt);
  const now = new Date();

  const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round(
    (dateDay.getTime() - nowDay.getTime()) / (1000 * 60 * 60 * 24),
  );

  if (Math.abs(diffDays) <= 1) {
    const hours = date.getHours();
    const minutes = date.getMinutes();
    const ampm = hours >= 12 ? "pm" : "am";
    const displayHours = hours % 12 || 12;
    const timeStr =
      minutes === 0
        ? `${displayHours}${ampm}`
        : `${displayHours}:${minutes.toString().padStart(2, "0")}${ampm}`;

    if (diffDays === -1) return `yesterday at ${timeStr}`;
    if (diffDays === 1) return `tomorrow at ${timeStr}`;
    return `today at ${timeStr}`;
  }

  return date.toLocaleString();
}

class JobRowView {
  view(vnode: m.Vnode<{ job: rpc.JobListItem }>) {
    const job = vnode.attrs.job;
    const statusClass =
      job.lastExitStatus === null
        ? "status-none"
        : job.lastExitStatus === 0
          ? "status-success"
          : "status-failure";

    return m("tr", { key: job.name, class: job.enabled ? "" : "disabled" }, [
      m(
        "td.job-name",
        m("a", { href: `/job/${encodeURIComponent(job.name)}` }, job.name),
      ),
      m("td.next-run", formatDateTime(job.nextScheduledTime)),
      m("td.last-run", formatDateTime(job.lastRunTime)),
      m(
        "td.status",
        { class: statusClass },
        job.lastExitStatus === null ? "-" : job.lastExitStatus.toString(),
      ),
      m(
        "td.time",
        job.lastWallTimeSecs !== null
          ? `${job.lastWallTimeSecs.toFixed(1)}s`
          : "",
      ),
      m("td.enabled", job.enabled ? "" : "disabled"),
    ]);
  }
}

class IndexPage {
  private jobs: rpc.JobListItem[];
  private controller: Controller;

  constructor() {
    this.jobs = [];
    this.controller = new Controller();
  }

  async oninit() {
    try {
      const data = await api.fetchJobs();
      this.jobs = data.jobs;
    } catch (e) {
      this.controller.pushError(`failed to load jobs: ${e}`);
      return;
    }
    m.redraw();
  }

  view() {
    return m(".page-container", [
      m(HeaderView, {
        controller: this.controller,
        title: "Jobs",
        links: [],
      }),
      m(".jobs-table-container", [
        m("table.jobs-table", [
          m("thead", [
            m("tr", [
              m("th", "Job"),
              m("th", "Next run"),
              m("th", "Last run"),
              m("th", "Status"),
              m("th", "Time"),
              m("th", ""),
            ]),
          ]),
          m(
            "tbody",
            this.jobs.map((job) => m(JobRowView, { job })),
          ),
        ]),
      ]),
    ]);
  }
}

export default IndexPage;
