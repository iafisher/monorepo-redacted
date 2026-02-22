import json

from iafisher_foundation.prelude import *
from lib import pdb
from .common import TokenUsage


def create_conversation(
    db: pdb.Connection,
    *,
    model: str,
    app_name: str,
    system_prompt: str,
    messages: List[StrDict],
    now: datetime.datetime
) -> int:
    return db.fetch_val(
        """
        INSERT INTO llm_v3_conversations(model, app_name, system_prompt, messages, time_created, time_last_updated)
        VALUES (%(model)s, %(app_name)s, %(system_prompt)s, %(messages)s, %(now)s, %(now)s)
        RETURNING conversation_id
        """,
        dict(
            model=model,
            app_name=app_name,
            system_prompt=system_prompt,
            messages=json.dumps(messages),
            now=now,
        ),
    )


@dataclass
class Conversation:
    conversation_id: int
    model: str
    system_prompt: str
    messages: List[StrDict]


def fetch_conversation(db: pdb.Connection, conversation_id: int) -> Conversation:
    return db.fetch_one(
        """
        SELECT conversation_id, model, system_prompt, messages
        FROM llm_v3_conversations
        WHERE conversation_id = %(conversation_id)s
        """,
        dict(conversation_id=conversation_id),
        t=pdb.t(Conversation),
    )


def fork_conversation(
    db: pdb.Connection, conversation_id: int, *, now: datetime.datetime
) -> Conversation:
    return db.fetch_one(
        """
        INSERT INTO llm_v3_conversations(model, system_prompt, messages, app_name, time_created, time_last_updated)
        SELECT model, system_prompt, messages, app_name, %(now)s AS time_created, %(now)s AS time_last_updated
        FROM llm_v3_conversations
        WHERE conversation_id = %(conversation_id)s
        RETURNING conversation_id, model, system_prompt, messages
        """,
        dict(conversation_id=conversation_id, now=now),
        t=pdb.t(Conversation),
    )


def fetch_last_token_usage(db: pdb.Connection, conversation_id: int) -> TokenUsage:
    return db.fetch_one(
        """
        SELECT
          input_tokens,
          output_tokens,
          reasoning_tokens,
          cache_read_tokens,
          cache_creation_tokens,
          total_tokens
        FROM llm_v3_api_requests
        WHERE conversation_id = %(conversation_id)s
        ORDER BY time_created DESC
        LIMIT 1
        """,
        dict(conversation_id=conversation_id),
        t=pdb.t(TokenUsage),
    )


def update_conversation(
    db: pdb.Connection,
    conversation_id: int,
    messages: List[StrDict],
    *,
    now: datetime.datetime
) -> None:
    db.execute(
        """
        UPDATE llm_v3_conversations
        SET messages = %(messages)s, time_last_updated = %(now)s
        WHERE conversation_id = %(conversation_id)s
        """,
        dict(messages=json.dumps(messages), now=now, conversation_id=conversation_id),
    )


def update_conversation_and_model(
    db: pdb.Connection,
    conversation_id: int,
    messages: List[StrDict],
    *,
    model: str,
    now: datetime.datetime
) -> None:
    db.execute(
        """
        UPDATE llm_v3_conversations
        SET messages = %(messages)s, model = %(model)s, time_last_updated = %(now)s
        WHERE conversation_id = %(conversation_id)s
        """,
        dict(
            messages=json.dumps(messages),
            model=model,
            now=now,
            conversation_id=conversation_id,
        ),
    )


def create_api_request(
    db: pdb.Connection,
    conversation_id: int,
    *,
    model: str,
    request_json: str,
    response_json: str,
    is_error: bool,
    token_usage: TokenUsage,
    now: datetime.datetime
) -> int:
    return db.fetch_val(
        """
        INSERT INTO llm_v3_api_requests(
          conversation_id,
          model,
          request_json,
          response_json,
          is_error,
          input_tokens,
          output_tokens,
          reasoning_tokens,
          cache_read_tokens,
          cache_creation_tokens,
          total_tokens,
          time_created
        )
        VALUES (
          %(conversation_id)s,
          %(model)s,
          %(request_json)s,
          %(response_json)s,
          %(is_error)s,
          %(input_tokens)s,
          %(output_tokens)s,
          %(reasoning_tokens)s,
          %(cache_read_tokens)s,
          %(cache_creation_tokens)s,
          %(total_tokens)s,
          %(now)s
        )
        RETURNING request_id
        """,
        dict(
            conversation_id=conversation_id,
            model=model,
            request_json=request_json,
            response_json=response_json,
            is_error=is_error,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            reasoning_tokens=token_usage.reasoning_tokens,
            cache_read_tokens=token_usage.cache_read_tokens,
            cache_creation_tokens=token_usage.cache_creation_tokens,
            total_tokens=token_usage.total_tokens,
            now=now,
        ),
    )
