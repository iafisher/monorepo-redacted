import json
import traceback
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory

from iafisher_foundation import colors, tabular
from iafisher_foundation.prelude import *
from lib import kgenv, llm, pdb
from . import commanddef
from .commanddef import CommandDef


@dataclass
class State:
    conversation_or_model: Union[str, llm.Conversation]
    options: llm.InferenceOptions

    def model_name(self) -> str:
        if isinstance(self.conversation_or_model, str):
            return self.conversation_or_model
        else:
            return self.conversation_or_model.model_name()


def loop(
    *,
    app_subname: str,
    system_prompt: str,
    model: str,
    hooks: llm.BaseHooks,
    tools: List[llm.BaseTool],
    resume_conversation_id: Optional[int] = None,
    options: llm.InferenceOptions,
) -> Optional[llm.Conversation]:
    app_name = f"llm2::{app_subname}"
    with pdb.connect(transaction_mode=pdb.TransactionMode.AUTOCOMMIT) as db:
        state = _setup_conversation(db, model, resume_conversation_id, options)
        print("(Press Opt+Enter to submit prompt.)\n")

        session = _create_prompt_session(app_subname, state)

        while True:
            try:
                message = session.prompt()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            try:
                assert isinstance(message, str)
                message = message.strip()
                if not message:
                    break

                if message.startswith("/"):
                    try:
                        command, command_arg = commanddef.parse_command(
                            command_defs, message
                        )
                    except commanddef.CommandParseError as e:
                        colors.print(colors.red(f"Error: {e}"))
                        continue

                    action = _handle_command(
                        db,
                        command,
                        command_arg,
                        state,
                        app_subname=app_subname,
                    )

                    if action is None:
                        continue
                else:
                    action = ActionPrompt(message)

                _send_prompt(
                    db,
                    state,
                    app_name,
                    system_prompt,
                    action,
                    tools,
                    hooks,
                    options,
                )
            except KeyboardInterrupt:
                print()
                continue

        if isinstance(state.conversation_or_model, llm.Conversation):
            conversation = state.conversation_or_model
            print()
            print(
                f"Conversation ended. You can resume it with `-resume {conversation.conversation_id}`."
            )
            return conversation
        else:
            return None


def _setup_conversation(
    db: pdb.Connection,
    model: str,
    resume_conversation_id: Optional[int],
    options: llm.InferenceOptions,
) -> State:
    if resume_conversation_id is not None:
        conversation = llm.Conversation.resume(db, resume_conversation_id)
        print(f"Resuming conversation ID: {conversation.conversation_id}")
        print(f"{pluralize(len(conversation.messages), 'previous message')}")
        for message in conversation.universal_messages():
            if not isinstance(message, llm.universal.TextMessage):
                continue

            print()
            match message.role:
                case "user":
                    colors.print(colors.yellow("> ") + message.text)
                case "assistant":
                    print(message.text)

        print()
        return State(conversation, options)

    return State(llm.canonicalize_model_name(model), options)


def _create_prompt_session(app_subname: str, state: State) -> PromptSession[str]:
    if isinstance(state.conversation_or_model, llm.Conversation):
        history_filename = f"llm2-{app_subname}-history-conversation-{state.conversation_or_model.conversation_id}"
    else:
        history_filename = f"llm2-{app_subname}-history"

    history_path: Path = kgenv.get_ian_dir() / "cache" / history_filename
    history = FileHistory(history_path)

    return PromptSession(
        ANSI(colors.yellow("> ")),
        multiline=True,
        prompt_continuation=ANSI(colors.yellow(". ")),
        history=history,
    )


def _handle_vote(
    _db: pdb.Connection,
    _conversation: Optional[llm.Conversation],
    _vote: str,
) -> None:
    # TODO(2026-01): Implement or delete this.
    colors.print(colors.red("Error: voting is currently not supported"))


def _handle_compact(
    db: pdb.Connection,
    state: State,
    *,
    app_subname: str,
) -> None:
    conversation = state.conversation_or_model
    if not isinstance(conversation, llm.Conversation):
        colors.print(colors.red("Error: cannot compact an empty conversation"))
        return

    previous_conversation_id = conversation.conversation_id
    original_system_prompt = conversation.system_prompt

    colors.print(colors.gray("Compacting conversation..."))

    # Create a temporary conversation with the compaction model
    compaction_conversation = llm.Conversation.start(
        db,
        model=llm.COMPACTION_MODEL,
        app_name=f"llm2::{app_subname}-compaction",
        system_prompt=COMPACT_SYSTEM_PROMPT,
    )

    conversation_text = _serialize_conversation_for_compaction(conversation)

    try:
        model_response = compaction_conversation.prompt(
            db,
            conversation_text + "\n\n" + COMPACT_PROMPT,
            options=llm.InferenceOptions(
                max_tokens=llm.MAX_TOKENS, temperature=1.0, reasoning=None
            ),
            hooks=llm.BaseHooks(),
            tools=[],
        )
    except Exception as e:
        print(traceback.format_exc())
        colors.print(colors.red(f"Error: failed to compact conversation: {e}"))
        return
    else:
        summary = model_response.output_text

    if not summary:
        colors.print(colors.red("Error: compaction model returned empty summary"))
        return

    state.conversation_or_model = llm.Conversation.start(
        db,
        model=state.model_name(),
        app_name=f"llm2::{app_subname}",
        system_prompt=original_system_prompt,
    )
    state.conversation_or_model.enqueue(
        db, f"Summary of conversation so far: {summary}"
    )

    colors.print(colors.gray("\nSummary of previous conversation:"))
    print(summary)
    print()
    print(
        f"Conversation compacted. Previous conversation ID: {previous_conversation_id}"
    )
    print(f"New conversation ID: {state.conversation_or_model.conversation_id}")


def _serialize_conversation_for_compaction(conversation: llm.Conversation) -> str:
    lines: List[str] = []

    if conversation.system_prompt:
        lines.append("=== System Prompt ===")
        lines.append(conversation.system_prompt)
        lines.append("")

    lines.append("=== Conversation ===")
    for message in conversation.messages:
        lines.append(json.dumps(message))
    return "\n".join(lines)


command_defs = [
    CommandDef("/clear", has_arg=False, help="Start a fresh conversation."),
    CommandDef("/compact", has_arg=False, help="Compact the current conversation."),
    CommandDef(
        "/cost", has_arg=False, help="Show the estimated cost of the conversation."
    ),
    CommandDef(
        "/downvote", has_arg=False, help="Downvote the last assistant response."
    ),
    CommandDef(
        "/fast",
        has_arg="maybe",
        help="Switch to a fast model, optionally sending a prompt.",
    ),
    CommandDef("/help", has_arg=False, help="Print this help message."),
    CommandDef("/model", has_arg=False, help="Print the current model."),
    CommandDef("/options", has_arg=False, help="Print current inference options."),
    CommandDef("/retry", has_arg=False, help="Retry the last request."),
    CommandDef("/switch", has_arg=True, help="Switch to a different model."),
    CommandDef(
        "/slow",
        has_arg="maybe",
        help="Switch to a slow model, optionally sending a prompt.",
    ),
    CommandDef("/undo-vote", has_arg=False, help="Undo the last up/down vote."),
    CommandDef("/upvote", has_arg=False, help="Upvote the last assistant response."),
]


COMPACT_SYSTEM_PROMPT = """\
You are a conversation summarization assistant. Your task is to create a concise summary of \
a conversation that preserves all the essential context and information.

The summary should:
1. Capture key facts, decisions, and conclusions from the conversation
2. Preserve important context that would be needed to continue the conversation naturally
3. Maintain any unresolved questions or action items
4. Be significantly shorter than the original while retaining all critical information
5. Be written as a clear, coherent narrative summary (not a list of bullet points)

The summary will be used to start a fresh conversation with the same participants, so it should \
provide enough context for the conversation to continue smoothly without referring back to the \
original messages.
"""

COMPACT_PROMPT = (
    "Please compact the current conversation as instructed in your system prompt."
)


@dataclass
class ActionPrompt:
    prompt: str


@dataclass
class ActionRetry:
    pass


Action = Union[ActionPrompt, ActionRetry]


def _handle_command(
    db: pdb.Connection,
    command: str,
    command_arg: str,
    state: State,
    *,
    app_subname: str,
) -> Optional[Action]:
    conversation = (
        state.conversation_or_model
        if isinstance(state.conversation_or_model, llm.Conversation)
        else None
    )
    match command:
        case "/clear":
            if conversation is None or len(conversation.messages) == 0:
                colors.print(colors.red("Error: cannot clear an empty conversation"))
            else:
                previous_conversation_id = conversation.conversation_id
                state.conversation_or_model = state.model_name()
                print(
                    "Conversation has been cleared."
                    + f" Previous conversation ID: {previous_conversation_id}\n"
                )
        case "/compact":
            _handle_compact(db, state, app_subname=app_subname)
            print()
        case "/cost":
            if conversation is None:
                colors.print(colors.red("Error: conversation is empty"))
            else:
                cost_breakdown = llm.estimate_conversation_cost(
                    db, conversation.conversation_id
                )
                if cost_breakdown is not None:
                    total_cost = sum(r.total_cost() for r in cost_breakdown.requests)
                    print(f"The estimated total cost is ${total_cost:.2f}.")
                else:
                    print(
                        "The total cost could not be determined.",
                    )
        case "/downvote":
            _handle_vote(db, conversation, "down")
        case "/fast":
            if conversation is not None:
                # TODO(2026-01): support this
                colors.print(colors.red("Error: cannot switch model mid-conversation"))
            else:
                state.conversation_or_model = llm.ANY_FAST_MODEL
                state.options = llm.InferenceOptions.fast()
                return ActionPrompt(command_arg)
        case "/help":
            print(commanddef.help_message(command_defs))
        case "/model":
            print(f"The current model is {state.model_name()}.\n")
        case "/options":
            options = state.options
            tabular.quicktable(
                ["Max tokens:", str(options.max_tokens)],
                ["Temperature:", str(options.temperature)],
                [
                    "Reasoning:",
                    str(options.reasoning.effort) if options.reasoning else "none",
                ],
            )
            print()
        case "/retry":
            return ActionRetry()
        case "/switch":
            if conversation is not None:
                conversation.switch_model(db, command_arg)
                print(f"The model is now {conversation.model_name()}.")
            else:
                try:
                    state.conversation_or_model = llm.canonicalize_model_name(
                        command_arg
                    )
                except Exception as e:
                    colors.print(
                        colors.red(
                            f"Error: unable to switch model to {command_arg!r}: {e}"
                        )
                    )
                else:
                    print(f"The model is now {state.model_name()}.")
                print()
        case "/slow":
            if conversation is not None:
                # TODO(2026-01): support this
                colors.print(colors.red("Error: cannot switch model mid-conversation"))
            else:
                state.conversation_or_model = llm.ANY_SLOW_MODEL
                state.options = llm.InferenceOptions.slow()
                return ActionPrompt(command_arg)
        case "/undo-vote":
            _handle_vote(db, conversation, "")
        case "/upvote":
            _handle_vote(db, conversation, "up")
        case _:
            pass


def _send_prompt(
    db: pdb.Connection,
    state: State,
    app_name: str,
    system_prompt: str,
    action: Action,
    tools: List[llm.BaseTool],
    hooks: llm.BaseHooks,
    options: llm.InferenceOptions,
) -> None:
    if not isinstance(state.conversation_or_model, llm.Conversation):
        if isinstance(action, ActionRetry):
            colors.error("Cannot retry when a conversation has not yet been started.")
            return

        state.conversation_or_model = llm.Conversation.start(
            db,
            model=state.model_name(),
            app_name=app_name,
            system_prompt=system_prompt,
        )
        colors.print(
            colors.gray(
                f"Conversation ID: {state.conversation_or_model.conversation_id}\n"
            )
        )

    print()
    try:
        match action:
            case ActionPrompt(message):
                state.conversation_or_model.prompt(
                    db, message, tools=tools, hooks=hooks, options=options
                )
            case ActionRetry():
                state.conversation_or_model.reprompt(
                    db, tools=tools, hooks=hooks, options=options
                )
    except KeyboardInterrupt:
        print()
        colors.print(colors.yellow("Canceled."))
    except Exception:
        print(traceback.format_exc())
        print()
        colors.error(f"Error: failed to prompt LLM (model: {state.model_name()})")
    else:
        print()
        tokens_used = state.conversation_or_model.count_tokens()
        token_limit = llm.get_token_limit(state.model_name())
        colors.print(colors.gray(f"Tokens: {tokens_used:,} / {token_limit:,}"))
