import feather from "feather-icons";
import m from "mithril";

import ModalController from "../common/modal";

import "./extension.scss";
import * as breadcrumbs from "./breadcrumbs";
import { callCodeMirrorBridge } from "./bridge";
import { backendLabel, copyedit } from "./copyedit";
import * as storage from "./storage";
import { BackendChoice, EditType } from "./types";

const HTML_ID_OVERLAY = "wikitidy-overlay";
const HTML_ID_STATUS = "wikitidy-status";

const BACKEND_CHOICES: BackendChoice[] = ["hard-coded", "localhost", "prod"];

class WikitidyApp {
  private status = "";
  private busy = false;
  private backend: BackendChoice = "prod";
  private modal = new ModalController();

  async oninit() {
    const saved = await storage.loadBackend();
    if (saved) {
      this.backend = saved;
    }

    breadcrumbs.statusStoredForPageReload();
    const status = await storage.loadStatus();
    if (status) {
      this.setStatus(status, false);
    }

    m.redraw();
  }

  view() {
    return m(
      "div",
      { id: HTML_ID_OVERLAY },
      m(
        "button.wikitidy-button",
        { onclick: () => this.onCopyEdit("llm"), disabled: this.busy },
        "copy-edit (llm)",
      ),
      m(
        "button.wikitidy-button",
        { onclick: () => this.onCopyEdit("regex"), disabled: this.busy },
        "copy-edit (regex)",
      ),
      m(
        "button.wikitidy-icon-button",
        { onclick: () => this.showSettings(), title: "Settings" },
        m.trust(
          feather.icons.settings.toSvg({ width: "16px", height: "16px" }),
        ),
      ),
      m(
        "div",
        { id: HTML_ID_STATUS, class: this.status === "" ? "hidden" : "" },
        this.status,
      ),
    );
  }

  private async onCopyEdit(editType: EditType): Promise<void> {
    const textarea = findTextarea();
    if (!textarea) {
      this.setStatus("textarea not found");
      return;
    }

    const text = textarea.value;
    if (text.trim() === "") {
      this.setStatus("textarea empty");
      return;
    }

    this.busy = true;
    this.setStatus("sent request");

    try {
      const now = Date.now();
      const edited = await copyedit(text, this.backend, editType);
      const elapsed = Date.now() - now;
      await writeEditorText(edited);
      setEditSummary();

      breadcrumbs.statusStoredForPageReload(); // persist here
      this.setStatus(`finished in ${(elapsed / 1000).toFixed(2)}s`, true);

      setTimeout(() => this.clearStatus(), 5000);
      setTimeout(() => showDiff());
      console.log(
        `wikitidy: edited page: ${text.length} --> ${edited.length} char(s)`,
      );
    } catch (error) {
      let errorString = String(error);
      if (!errorString.toLowerCase().startsWith("error")) {
        errorString = `error: ${errorString}`;
      }
      this.setStatus(errorString);
    } finally {
      this.busy = false;
      m.redraw();
    }
  }

  private showSettings(): void {
    this.modal.show(
      m(".wikitidy-modal", [
        m("h2", "Backend"),
        m(
          ".options",
          BACKEND_CHOICES.map((choice) =>
            m("label", [
              m("input", {
                type: "radio",
                name: "backend",
                checked: this.backend === choice,
                onchange: () => this.setBackend(choice),
              }),
              m("span", backendLabel(choice)),
            ]),
          ),
        ),
        m(
          ".actions",
          m(
            "button",
            {
              onclick: () => this.modal.hide(),
            },
            "Close",
          ),
        ),
      ]),
    );
  }

  private setBackend(choice: BackendChoice): void {
    this.backend = choice;
    storage.setBackend(choice);
  }

  private clearStatus(): void {
    this.status = "";
    m.redraw();
  }

  private setStatus(message: string, persist: boolean = false): void {
    const timeStr = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    this.status = `${timeStr}: ${message}`;
    m.redraw();
    console.log(`wikitidy: status: ${message}`);
    if (persist) {
      storage.setStatus(message);
    } else {
      breadcrumbs.statusStoredForPageReload();
      storage.setStatus("");
    }
  }
}

function init(): void {
  if (!findTextarea()) {
    console.log("wikitidy: textarea not found, aborting init");
    return;
  }

  if (document.getElementById(HTML_ID_OVERLAY)) {
    console.log(
      `wikitidy: overlay element (${HTML_ID_OVERLAY}) already exists, aborting init`,
    );
    return;
  }

  const container = document.createElement("div");
  document.body.appendChild(container);
  m.mount(container, new WikitidyApp());
  console.log("wikitidy: initialized");
}

async function writeEditorText(text: string): Promise<void> {
  const response = await callCodeMirrorBridge(text);
  if (!!response.error) {
    throw new Error(response.error);
  }
}

function setEditSummary(): void {
  const inputElement = document.getElementById("wpSummary") as HTMLInputElement;
  inputElement.value = "wikitidy: copy-edit";
}

function showDiff(): void {
  const diffButton = document.getElementById("wpDiff") as HTMLInputElement;
  diffButton.click();
}

function findTextarea(): HTMLTextAreaElement | null {
  return document.getElementById("wpTextbox1") as HTMLTextAreaElement | null;
}

// The initial HTTP response already contains the <textarea> we need, so it's safe to call
// `init` immediately.
init();
