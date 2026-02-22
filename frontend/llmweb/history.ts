import m from "mithril";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import * as api from "./api";
import * as rpc from "./rpc";

class HistoryItemView {
  view(vnode: m.Vnode<{ conv: rpc.FetchConversationsResponseItem }>) {
    const conv = vnode.attrs.conv;
    return m(
      "a.conversation-item",
      {
        key: conv.conversationId,
        href: "/conversation/" + conv.conversationId,
      },
      [
        m(".conversation-title", [
          m("span", conv.title || "Untitled conversation"),
          m(
            "span.message-count",
            `${conv.messageCount} message${conv.messageCount === 1 ? "" : "s"}`,
          ),
        ]),
        m(
          ".conversation-date",
          new Date(conv.timeCreated).toLocaleDateString(),
        ),
      ],
    );
  }
}

class HistoryPage {
  private conversations: rpc.FetchConversationsResponseItem[];
  private controller: Controller;

  constructor() {
    this.conversations = [];
    this.controller = new Controller();
  }

  async oninit() {
    try {
      const data = await api.fetchAllConversations();
      this.conversations = data.conversations;
    } catch (e) {
      this.controller.pushError(`failed to load conversations: ${e}`);
      return;
    }
    m.redraw();
  }

  view() {
    return m(".page-container", [
      m(HeaderView, {
        controller: this.controller,
        title: "Conversations",
        links: [{ text: "+ New", href: "/" }],
      }),
      m(
        ".conversations-list",
        this.conversations.map((conv) => m(HistoryItemView, { conv })),
      ),
    ]);
  }
}

export default HistoryPage;
