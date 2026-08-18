import m from "mithril";
import MarkdownIt from "markdown-it";

import Controller from "../common/controller";
import HeaderView from "../common/header";
import { formatTimestamp, isInDev } from "../common/utils";
import * as api from "./api";
import * as rpc from "./rpc";

const DEFAULT_MODEL = "claude-sonnet";

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
  loadingStatus: string | null;
  inputText: string;
  selectedModel: string;
  inferenceMode: string;
  webSearchEnabled: boolean;
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
  if (!message || !!state.loadingStatus) return;

  state.loadingStatus = "Query pending.";

  function onError(error: string) {
    state.controller.pushError(error);
    state.messages.push({
      role: "error",
      content: error,
      summary: "",
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

  let thinkingWords = 0;
  let textWords = 0;
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
    await api.prompt(
      conversationId,
      message,
      state.inferenceMode,
      state.webSearchEnabled,
      (event) => {
        if (event.chunkType === "message_created") {
          if (event.message.role === "user") {
            // Don't erase the input box until the text has been stored in the database.
            state.inputText = "";
            state.messages.push(event.message);
          } else if (event.message.role === "websearch") {
            state.loadingStatus = "Searching the web.";
          } else if (
            event.message.role === "assistant" ||
            event.message.role === "citations"
          ) {
            state.loadingStatus = null;
            state.messages.push(event.message);
          } else if (event.message.role === "error") {
            onError(event.message.content);
          }
        } else if (event.chunkType === "error") {
          onError(event.error);
        } else if (event.chunkType === "assistant_response_started") {
          state.loadingStatus = "Query received.";
        } else if (event.chunkType === "text") {
          textWords += countWordsInaccurately(event.payload);
          state.loadingStatus = `Response generating: ${pluralize(textWords, "word")}.`;
        } else if (event.chunkType === "thinking") {
          thinkingWords += countWordsInaccurately(event.payload);
          state.loadingStatus = `Model thinking: ${pluralize(thinkingWords, "word")}.`;
        } else if (event.chunkType === "token_count") {
          state.tokenCount = event.count;
        } else if (event.chunkType === "summary_started") {
          state.loadingStatus = `Summarizing: ${pluralize(textWords, "word")}.`;
        }

        m.redraw();
        scrollToBottom();
      },
    );
  } catch (error: any) {
    onError("Failed to send message: " + error.message);
    m.redraw();
  }

  state.loadingStatus = null;

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

function pluralize(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function countWordsInaccurately(text: string): number {
  return text.split(" ").length;
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
      if (!state.loadingStatus) {
        sendMessage(state);
      }
    } else if (e.metaKey || e.ctrlKey || e.altKey) {
      // On desktop: Cmd/Ctrl/Alt+Enter submits
      e.preventDefault();
      if (!state.loadingStatus) {
        sendMessage(state);
      }
    }
    // Otherwise, allow default Enter behavior (new line)
  }
}

class MessageFooterView {
  view(vnode: m.Vnode<{ state: ChatState; msg: FrontendMessage }>) {
    const msg = vnode.attrs.msg;
    return m(".message-footer", [
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
    let content, originalContent;
    let originalContentWords = 0;
    if (msg.isLoading) {
      content = m("span.loading-indicator");
    } else {
      if (msg.role === "citations") {
        content = m.trust(md.render(formatCitationsMessage(msg.content)));
      } else if (msg.role === "websearch") {
        content = m.trust(md.render(formatWebSearchMessage(msg.content)));
      } else if (!!msg.summary) {
        originalContent = m.trust(md.render(msg.content));
        originalContentWords = countWordsInaccurately(msg.content);
        content = m.trust(md.render(msg.summary));
      } else {
        content = m.trust(md.render(msg.content));
      }
    }
    return m(".message", { class: msg.role }, [
      m(".message-divider", msg.role),
      m(".message-content", content),
      !!originalContent
        ? m("details", [
            m(
              "summary",
              `Original message (${pluralize(originalContentWords, "word")})`,
            ),
            m(".message-content", originalContent),
          ])
        : null,
      m(MessageFooterView, { state, msg }),
    ]);
  }
}

class ModelSelectorView {
  view(vnode: m.Vnode<{ state: ChatState }>) {
    const state = vnode.attrs.state;
    const hasConversation = state.conversationId !== null;
    const models = [
      { value: "claude-sonnet", label: "Sonnet" },
      { value: "claude-opus", label: "Opus" },
      { value: "claude-haiku", label: "Haiku" },
      { value: "terra", label: "GPT 5.6 Terra" },
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

    const inferenceModeOptions = ["normal", "fast", "slow", "summary"];
    return m(".model-selector", [
      m("label", [
        "Model: ",
        hasConversation
          ? state.selectedModel
          : m(
              "select",
              {
                value: state.selectedModel,
                oninput: (e: InputEvent) => {
                  state.selectedModel = (e.target as HTMLSelectElement).value;
                },
              },
              models.map((model) =>
                m("option", { value: model.value }, model.label),
              ),
            ),
      ]),
      m("label", [
        "Mode: ",
        m(
          "select",
          {
            value: state.inferenceMode,
            oninput: (e: InputEvent) => {
              state.inferenceMode = (e.target as HTMLSelectElement).value;
            },
          },
          inferenceModeOptions.map((option) =>
            m("option", { value: option }, option),
          ),
        ),
      ]),
      m("label.checkbox-container", [
        m("input", {
          type: "checkbox",
          checked: state.webSearchEnabled,
          onchange: (e: InputEvent) => {
            state.webSearchEnabled = (e.target as HTMLInputElement).checked;
          },
        }),
        "Web search",
      ]),
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

class MessagesView {
  view(vnode: m.Vnode<{ state: ChatState }>) {
    const state = vnode.attrs.state;
    let messages = state.messages.slice();

    if (!!state.loadingStatus) {
      messages.push({
        role: "assistant",
        content: state.loadingStatus,
        summary: "",
        messageId: -1,
        vote: "",
        timeCreated: "",
      });
    }

    return m(
      ".messages-container",
      messages.map((msg, index) => m(MessageView, { state, msg, key: index })),
    );
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
        m(ChatInfoView, { llmConversationId: state.llmConversationId }),
        m(MessagesView, { state }),
        m(ModelSelectorView, { state }),
        m(".input-container", [
          m("textarea", {
            value: state.inputText,
            oninput: (e: InputEvent) =>
              (state.inputText = (e.target as HTMLInputElement).value),
            onkeydown: (e: KeyboardEvent) => handleKeyDown(e, state),
            oncreate: (vnode) => (vnode.dom as any).focus(),
            autocorrect: "off",
            autocomplete: "off",
            placeholder: "Type /help to see available commands.",
          }),
          m(".footer", [
            m("div", isMobileDevice() ? "Enter to send" : "⌥+Enter to send"),
            state.tokenCount !== null
              ? m(
                  ".token-count",
                  `${state.tokenCount.toLocaleString("en-US")} token${state.tokenCount === 1 ? "" : "s"} used`,
                )
              : null,
          ]),
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
      loadingStatus: null,
      selectedModel: DEFAULT_MODEL,
      inferenceMode: "normal",
      webSearchEnabled: false,
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
      this.state.selectedModel = DEFAULT_MODEL;
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
