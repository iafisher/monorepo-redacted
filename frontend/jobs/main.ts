import m from "mithril";

import "./jobs.scss";

import IndexPage from "./index";
import JobDetailPage from "./job";
import LogPage from "./log";

m.route.prefix = "";

m.route(document.body, "/", {
  "/": IndexPage,
  "/job/:jobName": JobDetailPage,
  "/log/:jobName/:timestamp": LogPage,
});
