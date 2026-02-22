import {
  CodeMirrorBridgeRequest,
  CodeMirrorBridgeResponse,
} from "./codemirror";

declare const chrome: {
  runtime: {
    getURL: (path: string) => string;
  };
};

let codeMirrorBridgePromise: Promise<void> | null = null;

function ensureCodeMirrorBridge(): Promise<void> {
  if (codeMirrorBridgePromise) {
    return codeMirrorBridgePromise;
  }

  codeMirrorBridgePromise = new Promise((resolve) => {
    const existing = document.querySelector(
      "script[data-wikitidy]",
    ) as HTMLScriptElement | null;
    if (existing) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("codemirror.js");
    script.dataset.wikitidy = "true";
    script.async = false;
    script.addEventListener("load", () => resolve());
    script.addEventListener("error", () => resolve());
    document.documentElement.appendChild(script);
  });

  return codeMirrorBridgePromise;
}

export function callCodeMirrorBridge(
  value: string,
): Promise<CodeMirrorBridgeResponse> {
  const id = `${Date.now()}-${Math.random()}`;
  const request: CodeMirrorBridgeRequest = {
    type: "wikitidy",
    id,
    value,
  };

  const origin = window.location.origin;
  return new Promise((resolve) => {
    let done = false;
    const listener = (event: MessageEvent) => {
      if (event.source !== window || event.origin !== origin) {
        return;
      }
      const data = event.data as CodeMirrorBridgeResponse;
      if (!data || data.type !== "wikitidy" || data.id !== id) {
        return;
      }
      done = true;
      window.removeEventListener("message", listener);
      resolve(data);
    };

    window.addEventListener("message", listener);
    ensureCodeMirrorBridge().then(() => {
      window.postMessage(request, origin);
    });

    setTimeout(() => {
      if (done) {
        return;
      }
      window.removeEventListener("message", listener);
      resolve({
        type: "wikitidy",
        id,
        error: "CodeMirror bridge timed out",
      });
    }, 2000);
  });
}
