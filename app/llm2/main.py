import time
from decimal import Decimal
from typing import Literal

from app.llm2.embeddings import cmd as embeddings_cmd
from app.llm2.chat import main as main_chat
from app.llm2.code import main as main_code
from app.llm2.code_alone import cmd as code_alone_cmd
from app.llm2.codereview import main as main_codereview
from app.llm2.proofread import main as main_proofread
from app.llm2.summarize_titles import main as main_summarize_titles
from app.llm2.trace import cmd as trace_cmd
from iafisher import colors, tabular
from iafisher.prelude import *
from lib import command, iterhelper, llm, pgdb


def main_conversations_count_tokens(conversation_id: int) -> None:
    with pgdb.connect() as db:
        conversation = llm.Conversation.resume(db, conversation_id)

    print(f"{conversation.count_tokens():,}")


def main_conversations_estimate_cost(conversation_id: int) -> None:
    with pgdb.connect() as db:
        cost_breakdown = llm.estimate_conversation_cost(db, conversation_id)

    if cost_breakdown is None:
        print("No token pricing information available for this model.")
    else:

        def usd(x: Union[Decimal, Literal[0]]) -> str:
            return f"${x:.2f}"

        table = tabular.Table()
        reqs = cost_breakdown.requests
        table.row(["Input tokens", usd(sum(r.input_token_cost() for r in reqs))])
        table.row(["Output tokens", usd(sum(r.output_token_cost() for r in reqs))])
        table.row(
            ["Reasoning tokens", usd(sum(r.reasoning_token_cost() for r in reqs))]
        )
        table.row(
            ["Cache read tokens", usd(sum(r.cache_read_token_cost() for r in reqs))]
        )
        table.row(
            [
                "Cache creation tokens",
                usd(sum(r.cache_creation_token_cost() for r in reqs)),
            ]
        )
        table.row(["Total", usd(sum(r.total_cost() for r in reqs))])
        table.flush()


def main_conversations_list() -> None:
    table = tabular.Table()
    table.header(["ID", "App", "Messages", "Tokens", "Model", "Last updated at"])
    with pgdb.connect() as db:
        datefmt = "%Y-%m-%d %I:%M %p"
        for conversation_from_db in fetch_conversations(db):
            token_count = conversation_from_db.token_count
            table.row(
                [
                    conversation_from_db.conversation_id,
                    conversation_from_db.app_name,
                    conversation_from_db.message_count,
                    f"{token_count:,}" if token_count is not None else "",
                    conversation_from_db.model or "",
                    conversation_from_db.time_last_updated.strftime(datefmt),
                ]
            )
    table.flush()


@dataclass
class ConversationFromDatabase:
    conversation_id: int
    app_name: str
    message_count: int
    token_count: Optional[int]
    model: str
    time_last_updated: dt.datetime


def fetch_conversations(db: pgdb.Connection) -> List[ConversationFromDatabase]:
    return db.fetch_all(
        """
        SELECT
          c.conversation_id,
          c.app_name,
          jsonb_array_length(c.messages) AS message_count,
          r.total_tokens AS token_count,
          c.model,
          c.time_last_updated
        FROM llm_v3_conversations c
        LEFT JOIN LATERAL (
          SELECT r.*
          FROM llm_v3_api_requests r
          WHERE c.conversation_id = r.conversation_id
          ORDER BY r.request_id DESC
          LIMIT 1
        ) r ON TRUE
        ORDER BY c.time_last_updated
        """,
        t=pgdb.t(ConversationFromDatabase),
    )


def main_conversations_replay(
    conversation_id: int,
    *,
    raw: bool,
    roundtrip: Annotated[
        bool,
        command.Extra(
            help="round-trip the conversation through the universal message format"
        ),
    ],
) -> None:
    with pgdb.connect() as db:
        conversation = llm.Conversation.resume(db, conversation_id)
        print(f"Model: {conversation.model_name()}\n")
        if roundtrip:
            messages = conversation._api.from_universal_messages(
                conversation.universal_messages()
            )
            for message, is_last in iterhelper.iter_is_last(messages):
                print(message)
                if not is_last:
                    print()
        elif raw:
            for message, is_last in iterhelper.iter_is_last(conversation.messages):
                print(message)
                if not is_last:
                    print()
        else:
            for message, is_last in iterhelper.iter_is_last(
                conversation.universal_messages()
            ):
                colors.print(colors.yellow(f"{message.role}> "))
                print(message)
                if not is_last:
                    print()


ONESHOT_SYSTEM_PROMPT = """\
You are responding to a user on the command-line via a `oneshot` command. In most cases,
you will simply respond to the user's request and there will be no further conversation.

Be concise.
"""


def main_oneshot(
    words: List[str],
    *,
    model: str = llm.ANY_FAST_MODEL,
    file: Annotated[
        Optional[pathlib.Path],
        command.Extra(help="include the text of the file as additional context"),
    ],
    inference: str = "fast",
) -> None:
    prompt = " ".join(words)
    if file is not None:
        prompt = f'<file path="{file}">{file.read_text()}</file>\n\n' + prompt

    match inference:
        case "fast":
            options = llm.InferenceOptions.fast()
        case "normal":
            options = llm.InferenceOptions.normal()
        case "slow":
            options = llm.InferenceOptions.slow()
        case x:
            raise KgError("unknown value for -inference flag", value=x)

    with pgdb.connect() as db:
        llm.oneshot(
            db,
            prompt,
            model=model,
            system_prompt=ONESHOT_SYSTEM_PROMPT,
            app_name="llm2::oneshot",
            options=options,
            hooks=llm.PrintTextHook(),
        )
        print()


def main_test_model(model: str) -> None:
    model = llm.canonicalize_model_name(model)
    print(f"Testing model: {model}")
    print()

    failures = 0
    with pgdb.connect() as db:

        def oneshot(prompt: str, options: llm.InferenceOptions) -> llm.ModelResponse:
            return llm.oneshot(
                db,
                prompt,
                model=model,
                system_prompt="",
                app_name="llm2::test",
                options=options,
                hooks=llm.BaseHooks(),
            )

        def do_test(
            label: str,
            prompt: str,
            options: llm.InferenceOptions,
            check_response: Callable[[llm.ModelResponse], bool],
        ) -> None:
            nonlocal failures

            print(f"==> testing {label}... ", end="", flush=True)
            options = llm.InferenceOptions.normal()
            start_time = time.monotonic()
            response = oneshot(prompt, options)
            end_time = time.monotonic()
            duration_secs = end_time - start_time

            if check_response(response):
                tokens = response.token_usage.total_tokens
                print(f"passed ({duration_secs:.1f}s, {tokens:,} tokens)")
            else:
                failures += 1
                print("FAILED")
                print()
                print("Model response:", response.output_text)
                print()

        prompt = "What is the capital of Saudi Arabia? Answer in one sentence."

        def check_response(response: llm.ModelResponse) -> bool:
            return "riyadh" in response.output_text.lower()

        do_test("normal options", prompt, llm.InferenceOptions.normal(), check_response)
        do_test("fast options", prompt, llm.InferenceOptions.fast(), check_response)
        do_test("slow options", prompt, llm.InferenceOptions.slow(), check_response)

    if failures > 0:
        sys.exit(1)


conversations_cmd = command.Group(help="Manage LLM conversations.")
conversations_cmd.add2(
    "count-tokens",
    main_conversations_count_tokens,
    help="Count tokens in a conversation.",
)
conversations_cmd.add2(
    "estimate-cost",
    main_conversations_estimate_cost,
    help="Estimate dollar cost of conversation.",
)
conversations_cmd.add2("list", main_conversations_list, help="List conversations.")
conversations_cmd.add2("replay", main_conversations_replay)

test_cmd = command.Group()
test_cmd.add2("model", main_test_model)

# TODO(2026-01): Split some of these off into their own top-level commands?
cmd = command.Group()
cmd.add2("chat", main_chat, help="Chat with an LLM on the command line.")
cmd.add2("code", main_code)
cmd.add("code-alone", code_alone_cmd)
cmd.add2("codereview", main_codereview)
cmd.add("conversations", conversations_cmd)
cmd.add("embeddings", embeddings_cmd)
cmd.add2("oneshot", main_oneshot, help="Respond to a prompt and exit.")
cmd.add2("proofread", main_proofread)
cmd.add2("summarize-titles", main_summarize_titles, less_logging=False)
cmd.add("test", test_cmd)
cmd.add("trace", trace_cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
