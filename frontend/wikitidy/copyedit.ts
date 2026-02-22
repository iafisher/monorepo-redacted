import * as rpc from "./rpc";
import { BackendChoice, EditType } from "./types";

type BackendConfig = {
  label: string;
  url: string | null;
};

const BACKENDS: Record<BackendChoice, BackendConfig> = {
  "hard-coded": {
    label: "hard-coded",
    url: null,
  },
  localhost: {
    label: "localhost",
    url: "http://localhost:7800",
  },
  prod: {
    label: "prod",
    url: "https://homeserver.tail5b2358.ts.net/wikipedia-api",
  },
};

export function backendLabel(choice: BackendChoice): string {
  return BACKENDS[choice].label;
}

export async function copyedit(
  text: string,
  backend: BackendChoice,
  editType: EditType,
): Promise<string> {
  if (backend === "hard-coded") {
    return "this is a test";
  }

  const serverUrl = BACKENDS[backend].url;
  if (!serverUrl) {
    throw new Error(`Missing server URL for backend: ${backend}`);
  }

  if (editType === "llm") {
    const request: rpc.CopyEditLLMRequest = { text, model: null };
    return sendRequest(serverUrl, editType, request);
  } else {
    const request: rpc.CopyEditRegexRequest = { text };
    return sendRequest(serverUrl, editType, request);
  }
}

async function sendRequest(
  serverUrl: string,
  editType: EditType,
  request: rpc.CopyEditLLMRequest | rpc.CopyEditRegexRequest,
): Promise<string> {
  const apiUrl = `${serverUrl}/tidy/${editType}`;
  console.log(`wikitidy: sending request to ${apiUrl}`);
  const response = await fetch(apiUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`request failed: ${response.status} ${body}`);
  }

  const data = (await response.json()) as {
    output?: rpc.CopyEditLLMResponse | rpc.CopyEditRegexResponse;
  };
  if (!data.output || typeof data.output.editedText !== "string") {
    throw new Error("unexpected response from server");
  }
  return data.output.editedText;
}
