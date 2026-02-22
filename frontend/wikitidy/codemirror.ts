type CodeMirrorWithSave = {
  setValue: (value: string) => void;
  save?: () => void;
};

export type CodeMirrorBridgeRequest = {
  type: "wikitidy";
  id: string;
  value: string;
};

export type CodeMirrorBridgeResponse = {
  type: "wikitidy";
  id: string;
  error?: string;
};

function findCodeMirror(): CodeMirrorWithSave | null {
  const wrapper = document.querySelector(".CodeMirror") as
    | (HTMLElement & { CodeMirror?: CodeMirrorWithSave })
    | null;
  return wrapper?.CodeMirror ?? null;
}

const origin = window.location.origin;

function handleMessage(event: MessageEvent): void {
  const response = handleMessageInner(event);
  if (!!response) {
    window.postMessage(response, origin);
  }
}

function handleMessageInner(
  event: MessageEvent,
): CodeMirrorBridgeResponse | null {
  if (event.source !== window || event.origin !== origin) {
    return null;
  }

  const data = event.data as CodeMirrorBridgeRequest;
  if (!data || data.type !== "wikitidy") {
    return null;
  }

  if (!data.value) {
    return {
      type: "wikitidy",
      id: data.id,
      error: "`data.value` is empty",
    };
  }

  const cm = findCodeMirror();
  if (!cm) {
    return {
      type: "wikitidy",
      id: data.id,
      error: "CodeMirror not found",
    };
  }

  try {
    cm.setValue(data.value);
    if (typeof cm.save === "function") {
      cm.save();
    }
    return {
      type: "wikitidy",
      id: data.id,
    };
  } catch (error) {
    return {
      type: "wikitidy",
      id: data.id,
      error: String(error),
    };
  }
}

function init(): void {
  const marker = window as unknown as { __wikipediaCopyeditBridge?: boolean };
  if (marker.__wikipediaCopyeditBridge) {
    return;
  }
  marker.__wikipediaCopyeditBridge = true;
  window.addEventListener("message", handleMessage);
}

init();
