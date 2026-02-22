import m from "mithril";

import "./llmweb.scss";

import ChatPage from "./chat";
import HistoryPage from "./history";
import TranscriptPage from "./transcript";

m.route.prefix = "";

m.route(document.body, "/", {
  "/": ChatPage,
  "/conversation/:id": ChatPage,
  "/conversations": HistoryPage,
  "/transcript/:id": TranscriptPage,
});
