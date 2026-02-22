import m from "mithril";
import MarkdownIt from "markdown-it";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import { formatTimestamp, isInDev } from "../common/utils";
import * as api from "./api";
import * as rpc from "./rpc";

const md = new MarkdownIt();

interface FrontendMessage extends rpc.Message {
  isLoading?: boolean;
}

interface ChatState {
  // TODO(2026-01): Make whole state a map from number to conversation details.
  controller: Controller;
  conversationId: number | null;
  llmConversationId: number | null;
  messages: (FrontendMessage | rpc.Message)[];
  inputText: string;
  isLoading: boolean;
  selectedModel: string;
  tokenCount: number | null;
}

async function loadConversation(state: ChatState, conversationId: number) {
  if (state.conversationId === conversationId) return;

  state.conversationId = conversationId;
  state.messages = [];
  state.inputText = "";
  m.redraw();

  let data;
  try {
    data = await api.fetchConversationById(conversationId);
  } catch (e) {
    state.controller.pushError(`failed to load conversation: ${e}`);
    return;
  }
  state.messages = data.messages;
  state.selectedModel = data.model;
  state.tokenCount = data.tokenCount;
  state.llmConversationId = data.llmConversationId;
  m.redraw();
  scrollToBottom();
}

class MessageAppender {
  private state: ChatState;
  private currentMessage: FrontendMessage | null;

  constructor(state: ChatState) {
    this.state = state;
    this.currentMessage = null;
  }

  messageCreated(message: any): void {
    if (message.role === "assistant") {
      // If it's an assistant message, then we had previously been accumulating a provisional
      // version of the message via text chunks. We should remove this provisional message and
      // replace it with the finalized message.
      //
      // TODO(2026-02): this is messy
      this.state.messages.pop();
    }

    this.state.messages.push(message);
  }

  error(error: string): void {
    this.state.messages.push({
      role: "error",
      content: error,
      messageId: -1,
      vote: "",
      timeCreated: "",
    });
  }

  responseStarted(): void {
    this.currentMessage = this.createEmptyMessage("assistant");
    this.state.messages.push(this.currentMessage);
  }

  text(text: string): void {
    if (this.currentMessage === null) {
      this.state.controller.pushError("'text' chunk received out-of-order");
      return;
    }

    this.pushNewMessageIfDifferentRole("assistant");
    this.currentMessage.isLoading = false;
    this.currentMessage.content += text;
  }

  thinking(text: string): void {
    if (this.currentMessage === null) {
      this.state.controller.pushError("'thinking' chunk received out-of-order");
      return;
    }

    this.pushNewMessageIfDifferentRole("thinking");
    this.currentMessage.isLoading = false;
    this.currentMessage.content += text;
  }

  private pushNewMessageIfDifferentRole(role: string): void {
    if (this.currentMessage === null) return;

    if (this.currentMessage.role !== role) {
      if (this.currentMessage.content.length === 0) {
        this.currentMessage.role = role;
      } else {
        this.currentMessage.isLoading = false;
        this.currentMessage = this.createEmptyMessage(role);
        this.state.messages.push(this.currentMessage);
      }
    }
  }

  private createEmptyMessage(role: string): FrontendMessage {
    return {
      role,
      content: "",
      isLoading: true,
      messageId: -1,
      vote: "",
      timeCreated: "",
    };
  }
}

function formatCitationsMessage(content: string): string {
  const payload = JSON.parse(content);
  const uniqueUrls: Map<string, string> = new Map();
  for (const data of payload) {
    uniqueUrls.set(data.url, data.title);
  }

  const r = [];
  for (const [url, title] of uniqueUrls) {
    if (!!title) {
      r.push(`- [${title}](${url})\n`);
    } else {
      r.push(`- <${url}>\n`);
    }
  }
  return r.join("");
}

function formatWebSearchMessage(content: string): string {
  const payload = JSON.parse(content);
  const r = ["Searching the web:\n\n"];
  for (const query of payload) {
    r.push(`- ${query}\n`);
  }
  return r.join("");
}

async function sendMessage(state: ChatState) {
  const message = state.inputText.trim();
  if (!message || state.isLoading) return;

  state.isLoading = true;

  function onError(error: string) {
    state.controller.pushError(error);
    state.messages.push({
      role: "error",
      content: error,
      messageId: -1,
      vote: "",
      timeCreated: "",
    });
  }

  let conversationId: number;
  if (!state.conversationId) {
    try {
      conversationId = (await api.startConversation(state.selectedModel))
        .conversationId;
    } catch (e) {
      onError(`failed to start conversation: ${e}`);
      return;
    }
    state.conversationId = conversationId;
  } else {
    conversationId = state.conversationId;
  }

  let assistantMessage: FrontendMessage | null = null;
  const appender = new MessageAppender(state);
  try {
    // Expected sequence:
    //
    //   - message_created for user message
    //   - assistant_response_started
    //   - 0 or more thinking chunks
    //   - 1 or more text chunks
    //   - message_created for assistant message
    //   - token_count chunk
    //
    await api.prompt(conversationId, message, (event) => {
      if (event.chunkType === "message_created") {
        if (event.message.role === "user") {
          // Don't erase the input box until the text has been stored in the database.
          state.inputText = "";
        }
        appender.messageCreated(event.message);
      } else if (event.chunkType === "error") {
        appender.error(event.error);
      } else if (event.chunkType === "assistant_response_started") {
        appender.responseStarted();
      } else if (event.chunkType === "text") {
        appender.text(event.payload);
      } else if (event.chunkType === "thinking") {
        appender.thinking(event.payload);
      } else if (event.chunkType == "token_count") {
        state.tokenCount = event.count;
      }

      m.redraw();
      scrollToBottom();
    });
  } catch (error: any) {
    onError("Failed to send message: " + error.message);
    m.redraw();
  }

  if (assistantMessage) {
    (assistantMessage as FrontendMessage).isLoading = false;
  }
  state.isLoading = false;

  // Update URL if we started a new conversation (use replaceState to avoid
  // triggering router which would clear state)
  const expectedPath = "/conversation/" + state.conversationId;
  if (window.location.pathname !== expectedPath) {
    history.replaceState(null, "", expectedPath);
  }

  m.redraw();
  scrollToBottom();

  // Return focus to textarea
  const textarea = document.querySelector(".input-container textarea");
  if (textarea) {
    (textarea as any).focus();
  }
}

function isScrolledNearBottom(): boolean {
  const container = document.querySelector(".chat-container");
  if (!container) return true;

  // Consider "near bottom" if within 50px of the bottom
  const threshold = 50;
  const scrollPosition = container.scrollTop + container.clientHeight;
  const scrollHeight = container.scrollHeight;

  return scrollHeight - scrollPosition <= threshold;
}

function scrollToBottom() {
  // Only auto-scroll if user hasn't manually scrolled up
  if (!isScrolledNearBottom()) {
    return;
  }

  const container = document.querySelector(".chat-container");
  if (container) {
    // Small delay to ensure DOM is updated
    setTimeout(() => {
      container.scrollTop = container.scrollHeight;
    }, 10);
  }
}

function isMobileDevice() {
  return (
    ("ontouchstart" in window || navigator.maxTouchPoints > 0) &&
    window.innerWidth < 768
  );
}

function handleKeyDown(e: KeyboardEvent, state: ChatState) {
  if (e.key === "Enter") {
    const mobile = isMobileDevice();
    if (mobile) {
      // On mobile: Enter submits
      e.preventDefault();
      if (!state.isLoading) {
        sendMessage(state);
      }
    } else if (e.metaKey || e.ctrlKey || e.altKey) {
      // On desktop: Cmd/Ctrl/Alt+Enter submits
      e.preventDefault();
      if (!state.isLoading) {
        sendMessage(state);
      }
    }
    // Otherwise, allow default Enter behavior (new line)
  }
}

async function handleVote(state: ChatState, messageId: number, vote: string) {
  try {
    await api.updateVote(messageId, vote);
    const message = state.messages.find((m) => m.messageId === messageId);
    if (message) {
      message.vote = vote;
    }
    m.redraw();
  } catch (error) {
    state.controller.pushError(`failed to save vote: ${error}`);
  }
}

class MessageFooterView {
  view(vnode: m.Vnode<{ state: ChatState; msg: FrontendMessage }>) {
    const msg = vnode.attrs.msg;
    const state = vnode.attrs.state;
    const isAssistant = msg.role === "assistant";
    const messageId = msg.messageId;
    return m(".message-footer", [
      isAssistant && messageId !== -1
        ? m(".vote-buttons", [
            m(
              "button.vote-btn",
              {
                class: msg.vote === "up" ? "active" : "",
                onclick: () =>
                  handleVote(state, messageId, msg.vote === "up" ? "" : "up"),
                title: "Upvote",
              },
              "▲",
            ),
            m(
              "button.vote-btn",
              {
                class: msg.vote === "down" ? "active" : "",
                onclick: () =>
                  handleVote(
                    state,
                    messageId,
                    msg.vote === "down" ? "" : "down",
                  ),
                title: "Downvote",
              },
              "▼",
            ),
          ])
        : null,
      msg.timeCreated
        ? m(".message-timestamp", formatTimestamp(new Date(msg.timeCreated)))
        : null,
    ]);
  }
}

class MessageView {
  view(vnode: m.Vnode<{ state: ChatState; msg: FrontendMessage }>) {
    const msg = vnode.attrs.msg;
    const state = vnode.attrs.state;
    let content;
    if (msg.isLoading) {
      content = m("span.loading-indicator");
    } else {
      if (msg.role === "citations") {
        content = m.trust(md.render(formatCitationsMessage(msg.content)));
      } else if (msg.role === "websearch") {
        content = m.trust(md.render(formatWebSearchMessage(msg.content)));
      } else {
        content = m.trust(md.render(msg.content));
      }
    }
    return m(".message", { class: msg.role }, [
      m(".message-divider", msg.role),
      m(".message-content", content),
      m(MessageFooterView, { state, msg }),
    ]);
  }
}

class ModelSelectorView {
  view(vnode: m.Vnode<{ state: ChatState }>) {
    const state = vnode.attrs.state;
    const hasConversation = state.conversationId !== null;
    const models = [
      { value: "claude-sonnet-4-5", label: "Sonnet" },
      { value: "claude-opus-4-6", label: "Opus" },
      { value: "claude-haiku-4-5", label: "Haiku" },
      { value: "gpt-5.1", label: "GPT 5" },
      { value: "gemini-2.5-pro", label: "Gemini 2.5" },
    ];

    if (isInDev()) {
      models.push({
        value: "claude-mock-local-tool-use",
        label: "Mock local tool use (Claude)",
      });
      models.push({
        value: "claude-mock-web-search",
        label: "Mock web search (Claude)",
      });
      models.push({
        value: "gemini-mock-web-search",
        label: "Mock web search (Gemini)",
      });
      models.push({
        value: "gpt-mock-web-search",
        label: "Mock web search (GPT)",
      });
    }

    return m(".model-selector-container", [
      m("label.model-selector-label", "Model:"),
      models.map((model) =>
        m(
          "button.model-selector-btn",
          {
            class: state.selectedModel === model.value ? "active" : "",
            disabled: hasConversation,
            onclick: () => {
              if (!hasConversation) {
                state.selectedModel = model.value;
              }
            },
          },
          model.label,
        ),
      ),
    ]);
  }
}

class ChatInfoView {
  view(vnode: m.Vnode<{ llmConversationId: number | null }>) {
    const llmConversationId = vnode.attrs.llmConversationId;
    return m(".chat-info", [
      llmConversationId !== null
        ? m(
            "a.conversation-id",
            { href: `/transcript/${llmConversationId}` },
            `Conversation ID: ${llmConversationId}`,
          )
        : null,
    ]);
  }
}

class ChatContainerView {
  view(vnode: m.Vnode<{ state: ChatState }>) {
    const state = vnode.attrs.state;
    const hasConversation = state.conversationId !== null;
    return m(".chat-container", [
      m(HeaderView, {
        controller: state.controller,
        title: "",
        links: [
          { text: "History", href: "/conversations" },
          hasConversation ? { text: "+ New", href: "/" } : null,
        ],
      }),
      m(".center-column", [
        m(ModelSelectorView, { state }),
        m(ChatInfoView, { llmConversationId: state.llmConversationId }),
        m(
          ".messages-container",
          state.messages.map((msg, index) =>
            m(MessageView, { state, msg, key: index }),
          ),
        ),
        state.tokenCount !== null
          ? m(
              ".token-count",
              `${state.tokenCount.toLocaleString("en-US")} token${state.tokenCount === 1 ? "" : "s"} used`,
            )
          : null,
        m(".input-container", [
          m("textarea", {
            value: state.inputText,
            oninput: (e: InputEvent) =>
              (state.inputText = (e.target as HTMLInputElement).value),
            onkeydown: (e: KeyboardEvent) => handleKeyDown(e, state),
            oncreate: (vnode) => (vnode.dom as any).focus(),
            autocorrect: "off",
            autocomplete: "off",
          }),
          m(
            ".input-hint",
            isMobileDevice() ? "Enter to send" : "⌥+Enter to send",
          ),
        ]),
      ]),
    ]);
  }
}

class ChatPage {
  private state: ChatState;

  constructor() {
    this.state = {
      controller: new Controller(),
      conversationId: null,
      llmConversationId: null,
      messages: [],
      inputText: "",
      isLoading: false,
      selectedModel: "claude-sonnet-4-5", // Default model
      tokenCount: null,
    };
  }

  async oninit() {
    const idStr = m.route.param("id");
    if (idStr) {
      this.state.selectedModel = "";
      loadConversation(this.state, parseInt(idStr));
    } else {
      // Reset state for new conversation
      this.state.conversationId = null;
      this.state.messages = [];
      this.state.inputText = "";
      this.state.selectedModel = "claude-sonnet-4-5";
    }
  }

  onupdate() {
    const idStr = m.route.param("id");
    if (idStr) {
      const id = parseInt(idStr);
      if (id !== this.state.conversationId) {
        loadConversation(this.state, id);
      }
    }
  }

  view() {
    return m(".page-container", [m(ChatContainerView, { state: this.state })]);
  }
}

export default ChatPage;
