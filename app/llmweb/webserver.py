import json
import queue
import pprint
import threading
import uuid
from typing import Literal

from flask import Response, render_template_string

from app.llm2 import commanddef
from app.llm2.commanddef import CommandDef
from app.llm2.code_alone import get_request_dir, Request as CodeAloneRequest
from app.llm2.redacted import *
from app.llmweb import db_models, rpc
from iafisher import timehelper
from iafisher.prelude import *  # noqa: F401
from lib import kgjson, llm, pgdb, webserver


app = webserver.make_app("llmweb", file=__file__)


TEMPLATE = webserver.make_template(title="kg: llm", static_file_name="llmweb")


SYSTEM_PROMPT = f"""\
You are a helpful assistant interacting with a user via a web interface.

Some basic information about the user:

{BASIC_INFORMATION}

You may or may not have a web search tool enabled. If enabled, you should use it
when asked for up-to-date or local information (e.g., restaurants in New York City),
or when explicitly requested. Do not use it for questions you can answer from your
own knowledge.

Maintain a professional, straightforward tone. Avoid humor, editorializing,
and casual asides. Present information clearly and let the user draw their
own conclusions. Be concise unless otherwise requested.

In your responses, do not use subheaders. If asked for instructions, provide
the single best answer and note any caveats; do not provide detailed alternatives
unless asked.

Your responses will be rendered as Markdown.
"""


@app.route("/")
@app.route("/conversations")
@app.route("/conversation/<int:_conversation_id>")
@app.route("/transcript/<int:_conversation_id>")
def frontend_page(*args: Any, **kwargs: Any):
    return render_template_string(TEMPLATE)


@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    with pgdb.connect() as db:
        conversations = db_fetch_conversations(db)

    return webserver.json_response2(
        rpc.FetchConversationsResponse(conversations=conversations)
    )


def db_fetch_conversations(
    db: pgdb.Connection,
) -> List[rpc.FetchConversationsResponseItem]:
    return db.fetch_all(
        pgdb.SQL(
            """
            SELECT w.conversation_id, w.title, l.model, w.time_created, COUNT(m.message_id) AS message_count
            FROM llmweb_conversations w
            LEFT JOIN llm_v3_conversations l
            ON w.llm_conversation_id = l.conversation_id
            LEFT JOIN llmweb_messages m
            ON m.conversation_id = w.conversation_id
            GROUP BY 1, 2, 3, 4
            ORDER BY w.time_created DESC
            """
        ),
        t=pgdb.t(rpc.FetchConversationsResponseItem),
    )


@app.route("/api/conversation/<int:conversation_id>", methods=["GET"])
def api_conversation(conversation_id: int):
    with pgdb.connect() as db:
        messages = db.fetch_all(
            """
            SELECT message_id, role, content, summary, vote, time_created
            FROM llmweb_messages
            WHERE conversation_id = %(conversation_id)s
            ORDER BY message_id
            """,
            dict(conversation_id=conversation_id),
            t=pgdb.t(rpc.Message),
        )

        model, raw_messages, llm_conversation_id = db.fetch_one(
            """
            SELECT model, messages, conversation_id
            FROM llm_v3_conversations
            WHERE conversation_id = (
                SELECT llm_conversation_id
                FROM llmweb_conversations
                WHERE conversation_id = %(conversation_id)s
            )
            """,
            dict(conversation_id=conversation_id),
            t=pgdb.tuple_row,
        )

    try:
        token_count = llm.count_tokens(model, raw_messages)
    except Exception:
        LOG.exception("failed to get token count for model: %r", model)
        token_count = -1

    response = rpc.ConversationResponse(
        model=model,
        messages=messages,
        token_count=token_count,
        llm_conversation_id=llm_conversation_id,
    )
    return webserver.json_response2(response)


@app.route("/api/start", methods=["POST"])
def api_start():
    rpc_request = webserver.request(rpc.StartRequest)
    model_name = rpc_request.model or llm.ClaudeModel.SONNET_LATEST

    try:
        model_name = llm.canonicalize_model_name(model_name)
    except KgError:
        return webserver.json_response_error(f"invalid model: {model_name}")

    with pgdb.connect() as db:
        now = timehelper.now()
        llm_conversation_id = llm.storage.create_conversation(
            db,
            model=model_name,
            app_name="llmweb",
            system_prompt=SYSTEM_PROMPT,
            messages=[],
            now=now,
        )
        conversation = insert_conversation(db, llm_conversation_id)

    response = rpc.StartResponse(conversation_id=conversation.conversation_id)
    return webserver.json_response2(response)


@app.route("/api/vote", methods=["POST"])
def api_vote():
    rpc_request = webserver.request(rpc.VoteRequest)
    if rpc_request.vote not in ("", "up", "down"):
        return webserver.json_response_error("vote must be '', 'up', or 'down'")

    with pgdb.connect() as db:
        db.execute(
            """
            UPDATE llmweb_messages
            SET vote = %(vote)s
            WHERE message_id = %(message_id)s
            """,
            dict(message_id=rpc_request.message_id, vote=rpc_request.vote),
        )

    return webserver.json_response2(rpc.VoteResponse())


@app.route("/api/transcript/<int:conversation_id>", methods=["GET"])
def api_transcript(conversation_id: int):
    with pgdb.connect() as db:
        conversation = llm.Conversation.resume(db, conversation_id)

    response = rpc.TranscriptResponse(
        raw=conversation.messages, universal=conversation.universal_messages()
    )
    return webserver.json_response2(response)


@dataclass
class ChunkText(kgjson.Base):
    payload: str
    chunk_type: Literal["text"] = "text"


@dataclass
class ChunkThinking(kgjson.Base):
    payload: str
    chunk_type: Literal["thinking"] = "thinking"


@dataclass
class ChunkAssistantResponseStarted(kgjson.Base):
    chunk_type: Literal["assistant_response_started"] = "assistant_response_started"


@dataclass
class ChunkSummaryStarted(kgjson.Base):
    chunk_type: Literal["summary_started"] = "summary_started"


@dataclass
class ChunkMessageCreated(kgjson.Base):
    message: db_models.Message
    chunk_type: Literal["message_created"] = "message_created"


@dataclass
class ChunkError(kgjson.Base):
    # The difference between `ChunkError` and `ChunkMessageCreated` with an `error` message is that
    # the latter was inserted into the database and includes, e.g., `message_id`.
    error: str
    chunk_type: Literal["error"] = "error"


@dataclass
class ChunkTokenCount(kgjson.Base):
    count: int
    chunk_type: Literal["token_count"] = "token_count"


@dataclass
class ChunkDone:
    chunk_type: Literal["done"] = "done"


Chunk = Union[
    ChunkText,
    ChunkThinking,
    ChunkAssistantResponseStarted,
    ChunkSummaryStarted,
    ChunkMessageCreated,
    ChunkError,
    ChunkTokenCount,
    ChunkDone,
]


class StreamingHooks(llm.BaseHooks):
    _text_builder: List[str]

    def __init__(
        self, db: pgdb.Connection, conversation_id: int, q: queue.Queue[Chunk]
    ):
        self.db = db
        self.conversation_id = conversation_id
        self.q = q

    @override
    def on_text_delta(self, text: str) -> None:
        self.q.put(ChunkText(text))

    @override
    def on_thinking_delta(self, text: str) -> None:
        self.q.put(ChunkThinking(text))

    @override
    def on_web_search(self, queries: List[str]) -> None:
        message = insert_message(
            self.db, self.conversation_id, "websearch", json.dumps(queries)
        )
        self.q.put(ChunkMessageCreated(message))


@app.route("/api/prompt", methods=["POST"])
def api_prompt():
    rpc_request = webserver.request(rpc.PromptRequest)
    conversation_id = rpc_request.conversation_id
    user_prompt = rpc_request.message.strip()

    q: queue.Queue[Chunk] = queue.Queue()

    def produce_chunks_inner(db: pgdb.Connection) -> None:
        if len(user_prompt) == 0:
            # In this case, we don't bother inserting a message into the database.
            q.put(ChunkError("The message was blank."))
            return

        llm_conversation_id = fetch_llm_conversation_id(db, conversation_id)
        conversation = llm.Conversation.resume(db, llm_conversation_id)

        user_message = insert_message(db, conversation_id, "user", user_prompt)
        q.put(ChunkMessageCreated(user_message))

        is_summary_mode = False
        match rpc_request.inference_mode:
            case None | "normal":
                options = llm.InferenceOptions.normal()
            case "fast":
                options = llm.InferenceOptions.fast()
            case "slow":
                options = llm.InferenceOptions.slow()
            case "summary":
                options = llm.InferenceOptions.normal()
                is_summary_mode = True
            case x:
                LOG.warning("got unknown inference options: %r", x)
                options = llm.InferenceOptions.normal()

        if user_prompt.startswith("/"):
            try:
                command, arg = commanddef.parse_command(command_defs, user_prompt)
            except commanddef.CommandParseError as e:
                message = insert_message(db, conversation_id, "error", str(e))
                q.put(ChunkMessageCreated(message))
                return

            match command:
                case "/code-alone":
                    request_id = enqueue_code_alone_request(llm_conversation_id, arg)
                    message = insert_message(
                        db,
                        conversation_id,
                        "system",
                        f"Request {request_id} has been enqueued.",
                    )
                    q.put(ChunkMessageCreated(message))
                    return
                case "/cost":
                    cost_breakdown = llm.estimate_conversation_cost(
                        db, llm_conversation_id
                    )
                    if cost_breakdown is not None:
                        total_cost = sum(
                            r.total_cost() for r in cost_breakdown.requests
                        )
                        message = insert_message(
                            db,
                            conversation_id,
                            "system",
                            f"The estimated total cost is ${total_cost:.2f}.",
                        )
                    else:
                        message = insert_message(
                            db,
                            conversation_id,
                            "system",
                            "The total cost could not be determined.",
                        )

                    q.put(ChunkMessageCreated(message))
                    return
                case "/dump":
                    dumped = pprint.pformat(conversation.messages, width=100)
                    message = insert_message(db, conversation_id, "system", dumped)
                    q.put(ChunkMessageCreated(message))
                    return
                case "/help":
                    message = insert_message(
                        db,
                        conversation_id,
                        "system",
                        commanddef.help_message(command_defs, as_markdown=True),
                    )
                    q.put(ChunkMessageCreated(message))
                    return
                case "/model":
                    message = insert_message(
                        db,
                        conversation_id,
                        "system",
                        f"The current model is {conversation.model_name()}.",
                    )
                    q.put(ChunkMessageCreated(message))
                    return
                case "/options":
                    reasoning = (
                        options.reasoning.effort if options.reasoning else "none"
                    )
                    message = insert_message(
                        db,
                        conversation_id,
                        "system",
                        f"Max tokens: {options.max_tokens}\nTemperature: {options.temperature}\nReasoning: {reasoning}",
                    )
                    q.put(ChunkMessageCreated(message))
                    return
                case "/switch":
                    previous_model = conversation.model_name()
                    conversation.switch_model(db, arg)
                    message = insert_message(
                        db,
                        conversation_id,
                        "system",
                        f"The model is now {conversation.model_name()} (was {previous_model}).",
                    )
                    q.put(ChunkMessageCreated(message))
                    return
                case _:
                    pass

        try:
            hooks = StreamingHooks(db, conversation_id, q)
            tools: List[llm.BaseTool] = (
                [llm.tools.WebSearchTool()]
                if opt_or(rpc_request.web_search_enabled, False)
                else []
            )
            q.put(ChunkAssistantResponseStarted())
            response = conversation.prompt(
                db, user_prompt, hooks=hooks, options=options, tools=tools
            )
        except Exception as e:
            LOG.exception("LLM call failed with error")
            error_message = insert_message(
                db, conversation_id, "error", f"LLM call failed with error: {e}"
            )
            q.put(ChunkMessageCreated(error_message))
        else:
            # TODO(2026-02): Thinking blocks are never stored to the database.

            if is_summary_mode and len(response.output_text.split()) > 50:
                q.put(ChunkSummaryStarted())
                summary_response = llm.oneshot(
                    db,
                    f"<query>\n{user_prompt}\n</query>\n\n<response>\n{response.output_text}\n</response>\n",
                    model=llm.GptModel.GPT_5_6_LUNA,
                    system_prompt=SUMMARY_PROMPT,
                    app_name="llmweb",
                    options=llm.InferenceOptions.fast(),
                )
                summary_text = summary_response.output_text
            else:
                summary_text = ""

            output_text = response.output_text
            assistant_message = insert_message(
                db, conversation_id, "assistant", output_text, summary=summary_text
            )
            q.put(ChunkMessageCreated(assistant_message))

            citations = get_citations(conversation, response)
            if len(citations) > 0:
                citations_message = insert_message(
                    db,
                    conversation_id,
                    "citations",
                    json.dumps(
                        [dataclasses.asdict(citation) for citation in citations]
                    ),
                )
                q.put(ChunkMessageCreated(citations_message))

            try:
                token_count = conversation.count_tokens()
            except Exception:
                LOG.exception(
                    "failed to get token count for model: %r", conversation.model_name()
                )
                token_count = -1

            q.put(ChunkTokenCount(token_count))

    def produce_chunks():
        with pgdb.connect() as db:
            try:
                produce_chunks_inner(db)
            except Exception as e:
                LOG.exception("LLM call failed with error")
                error_message_text = f"LLM call failed with error: {e}"
                try:
                    error_message = insert_message(
                        db, conversation_id, "error", error_message_text
                    )
                except Exception:
                    LOG.exception("could not save message to database")
                    q.put(ChunkError(error_message_text))
                else:
                    q.put(ChunkMessageCreated(error_message))

            q.put(ChunkDone())

    thread = threading.Thread(target=produce_chunks)
    thread.start()

    def consume_chunks():
        while True:
            timeout_secs = 120
            try:
                chunk = q.get(timeout=timeout_secs)
            except queue.Empty:
                # TODO(2026-01): Store this in the database?
                chunk = ChunkError(
                    f"The LLM call timed out after {pluralize(timeout_secs, 'second')}."
                )

            match chunk.chunk_type:
                case "done":
                    break
                case "error":
                    yield chunk.serialize(camel_case=True) + "\n"
                    break
                case _:
                    yield chunk.serialize(camel_case=True) + "\n"

    return Response(
        consume_chunks(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


SUMMARY_PROMPT = """\
Summarize the <response>...</response> block in 1-3 sentences.

Write the summary so that it can be substituted for the original message, e.g., don't
begin it with "The message says...".

Include the key points and questions but omit unnecessary details.

You are given the query that prompted the response in a <query>...</query> block for
context. Do not summarize the query, just the response.
"""


def get_citations(
    conversation: llm.Conversation, response: llm.ModelResponse
) -> List[llm.universal.Citation]:
    universal_messages = conversation._api.to_universal_messages(response.messages)
    if len(universal_messages) == 0:
        return []

    return flatten_list(
        [
            msg.citations
            for msg in universal_messages
            if isinstance(msg, llm.universal.TextMessage)
        ]
    )


def enqueue_code_alone_request(llm_conversation_id: int, prompt: str) -> uuid.UUID:
    request_dir = get_request_dir()
    request_dir.mkdir(parents=True, exist_ok=True)
    request_id = uuid.uuid4()

    request = CodeAloneRequest(
        request_id=str(request_id),
        llm_conversation_id=llm_conversation_id,
        prompt=prompt,
    )

    request.save(request_dir / f"request-{request_id}.json")
    return request_id


def fetch_llm_conversation_id(db: pgdb.Connection, conversation_id: int) -> int:
    return db.fetch_val(
        """
        SELECT llm_conversation_id
        FROM llmweb_conversations
        WHERE conversation_id = %(conversation_id)s
        """,
        dict(conversation_id=conversation_id),
    )


def insert_message(
    db: pgdb.Connection,
    conversation_id: int,
    role: Literal["user", "assistant", "system", "error", "citations", "websearch"],
    content: str,
    *,
    summary: str = "",
) -> db_models.Message:
    # TODO(2026-02): `role` should be split into `role` ('user' or 'assistant') and `type`.
    # One advantage of this is that I don't need to update the database constraint every time
    # I add a new message type.
    now = timehelper.now()
    return db.fetch_one(
        pgdb.SQL(
            """
            INSERT INTO llmweb_messages(conversation_id, role, content, summary, time_created)
            VALUES (%(conversation_id)s, %(role)s, %(content)s, %(summary)s, %(now)s)
            RETURNING {star}
            """
        ).format(star=db_models.Message.T.star),
        dict(
            conversation_id=conversation_id,
            role=role,
            content=content,
            summary=summary,
            now=now,
        ),
        t=pgdb.t(db_models.Message),
    )


def insert_conversation(
    db: pgdb.Connection, llm_conversation_id: int
) -> db_models.Conversation:
    now = timehelper.now()
    return db.fetch_one(
        pgdb.SQL(
            """
            INSERT INTO llmweb_conversations(llm_conversation_id, title, time_created)
            VALUES (%(llm_conversation_id)s, '', %(now)s)
            RETURNING {star}
            """
        ).format(star=db_models.Conversation.T.star),
        dict(llm_conversation_id=llm_conversation_id, now=now),
        t=pgdb.t(db_models.Conversation),
    )


command_defs = [
    CommandDef(
        "/code-alone",
        has_arg=True,
        help="Request the LLM to asynchronously execute a coding task in the monorepo.",
    ),
    CommandDef(
        "/cost", has_arg=False, help="Show the estimated cost of the conversation."
    ),
    CommandDef(
        "/dump", has_arg=False, help="Dump the conversation message state as JSON."
    ),
    CommandDef("/help", has_arg=False, help="Print this help message."),
    CommandDef("/model", has_arg=False, help="Print the current model."),
    CommandDef("/options", has_arg=False, help="Print current inference options."),
    CommandDef("/switch", has_arg=True, help="Switch to a different model."),
]


cmd = webserver.make_command(app, default_port=7600)
