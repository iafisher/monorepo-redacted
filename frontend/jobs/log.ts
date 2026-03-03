import m from "mithril";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import * as api from "./api";

class LogContentView {
  view(vnode: m.Vnode<{ content: string }>) {
    const { content } = vnode.attrs;
    if (content === "") {
      return m("p.empty-log-content", "The log file is empty.");
    } else {
      return m("pre.log-content", content);
    }
  }
}

class LogPage {
  private jobName: string;
  private timestamp: string;
  private logContent: string | null;
  private controller: Controller;

  constructor(vnode: m.Vnode<{ jobName: string; timestamp: string }>) {
    this.jobName = vnode.attrs.jobName;
    this.timestamp = vnode.attrs.timestamp;
    this.logContent = null;
    this.controller = new Controller();
  }

  async oninit(vnode: m.Vnode<{ jobName: string; timestamp: string }>) {
    this.jobName = vnode.attrs.jobName;
    this.timestamp = vnode.attrs.timestamp;
    try {
      this.logContent = (
        await api.fetchLog(this.jobName, this.timestamp)
      ).content;
    } catch (e) {
      this.controller.pushError(`failed to load log: ${e}`);
      return;
    }
    m.redraw();
  }

  view() {
    const title = `${this.jobName} - ${new Date(this.timestamp).toLocaleString()}`;

    if (this.logContent === null) {
      return m(".page-container", [
        m(HeaderView, {
          controller: this.controller,
          title: "Log",
          links: [
            { text: "← Job", href: `/job/${this.jobName}` },
            { text: "Home", href: "/" },
          ],
        }),
        m(".loading", "Loading..."),
      ]);
    }

    return m(".page-container", [
      m(HeaderView, {
        controller: this.controller,
        title: "Log",
        links: [
          { text: "← job", href: `/job/${this.jobName}` },
          { text: "home", href: "/" },
        ],
      }),
      m(".log-viewer", [
        m("h2", title),
        m(LogContentView, { content: this.logContent }),
      ]),
    ]);
  }
}

export default LogPage;
