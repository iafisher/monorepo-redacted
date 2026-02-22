export async function post(url: string, payload: object): Promise<any> {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error(`failed to fetch (url: ${url})`);
  }
  return await handleResponse(url, response);
}

export async function postStreaming(
  url: string,
  payload: object,
  onChunk: (chunk: any) => void,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.body === null) {
    throw new Error("response.body was null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || ""; // Keep incomplete line in buffer

    for (const line of lines) {
      try {
        const event = JSON.parse(line);
        onChunk(event);
      } catch (e) {
        throw new Error("failed to parse SSE event: " + line);
      }
    }
  }
}

export async function get(url: string): Promise<any> {
  const response = await fetch(url);
  return await handleResponse(url, response);
}

async function handleResponse(url: string, response: Response): Promise<any> {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`failed to parse response as JSON (url: ${url})`);
  }

  if (!!data.error) {
    throw new Error(data.error);
  } else if (response.status >= 400 && response.status < 600) {
    throw new Error(`got HTTP status ${response.status} (url: ${url})`);
  } else if (!!data.output) {
    return data.output;
  } else {
    throw new Error(`invalid RPC response (url: ${url})`);
  }
}
