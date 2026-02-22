import m from "mithril";
import MarkdownIt from "markdown-it";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import * as api from "./api";

const md = new MarkdownIt();

class MessageView {
  view(vnode: m.Vnode<{ msg: any }>) {
    const msg = vnode.attrs.msg;
    const classes = [msg.role];
    let msgContent;
    if (!!msg.text) {
      classes.push("text");
      msgContent = m.trust(md.render(msg.text));
    } else if (msg.thinking !== undefined) {
      classes.push("thinking");
      msgContent = msg.thinking;
    } else if (msg.toolInput !== undefined) {
      classes.push("tool-use-request");
      msgContent = `Tool name: ${msg.toolName}\n\nTool input:\n\n${JSON.stringify(msg.toolInput)}`;
    } else if (msg.toolOutput !== undefined) {
      classes.push("tool-use-response");
      let outputString;
      try {
        const output = JSON.parse(msg.toolOutput);
        if (typeof output === "string") {
          outputString = output;
        } else {
          outputString = msg.toolOutput;
        }
      } catch {
        outputString = msg.toolOutput;
      }
      msgContent = `Tool output:\n\n${outputString}`;
    } else {
      msgContent = JSON.stringify(msg.rawJson);
    }
    return m(".message", { class: classes.join(" ") }, [
      m(".message-divider", msg.role),
      m(".message-content", msgContent),
    ]);
  }
}

class TranscriptPage {
  private messages: any[];
  private controller: Controller;

  constructor() {
    this.messages = [];
    this.controller = new Controller();
  }

  async oninit() {
    const idStr = m.route.param("id");
    try {
      this.messages = (await api.fetchTranscript(parseInt(idStr))).universal;
    } catch (e) {
      this.controller.pushError(`failed to load transcript: ${e}`);
      return;
    }
    m.redraw();
  }

  view() {
    return m(".page-container.transcript-page", [
      m(HeaderView, {
        controller: this.controller,
        title: "",
        links: [
          { text: "History", href: "/conversations" },
          { text: "+ New", href: "/" },
        ],
      }),
      m(
        ".center-column",
        m(
          ".messages-list",
          this.messages.map((msg) => m(MessageView, { msg })),
        ),
      ),
    ]);
  }
}

export default TranscriptPage;
