import * as kgrpc from "../common/kgrpc";
import * as rpc from "./rpc";

export async function fetchConversationById(
  conversationId: number,
): Promise<rpc.ConversationResponse> {
  return await kgrpc.get(`/api/conversation/${conversationId}`);
}

export async function fetchAllConversations(): Promise<rpc.FetchConversationsResponse> {
  return await kgrpc.get("/api/conversations");
}

export async function startConversation(
  model: string,
): Promise<rpc.StartResponse> {
  const request: rpc.StartRequest = { model };
  return await kgrpc.post("/api/start", request);
}

export async function prompt(
  conversationId: number,
  message: string,
  inferenceMode: string | null,
  onChunk: (event: any) => void,
) {
  const request: rpc.PromptRequest = {
    conversationId,
    message,
    inferenceMode,
  };
  await kgrpc.postStreaming("/api/prompt", request, onChunk);
}

export async function fetchTranscript(
  conversationId: number,
): Promise<rpc.TranscriptResponse> {
  return await kgrpc.get(`/api/transcript/${conversationId}`);
}
