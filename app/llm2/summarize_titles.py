from iafisher_foundation.prelude import *
from lib import llm, pdb


def summarize_title(first_message: str) -> str:
    with pdb.connect() as db:
        response = llm.oneshot(
            db,
            f"Summarize this message in 5-7 words as a title:\n\n{first_message}",
            model=llm.CLAUDE_HAIKU_4_5,
            system_prompt="You are a helpful assistant that creates concise, descriptive titles."
            " The title should be in sentence case and begin with a capital letter."
            " Return only the title, without quotes or punctuation at the end.",
            app_name="llm2::summarize_titles",
            options=llm.InferenceOptions.fast(),
        )
        return response.output_text.strip()


def main(*, limit: Optional[int] = None) -> None:
    with pdb.connect() as db:
        conversations = db.fetch_all(
            """
            SELECT DISTINCT w.conversation_id
            FROM llmweb_conversations w
            JOIN llmweb_messages m ON w.conversation_id = m.conversation_id
            WHERE w.title = ''
            AND m.role = 'user'
            ORDER BY w.conversation_id
            """
            + (f"LIMIT {limit}" if limit is not None else ""),
            t=pdb.tuple_row,
        )

        if not conversations:
            LOG.info("No conversations with empty titles found")
            return

        LOG.info(f"Found {len(conversations)} conversations with empty titles")

        processed = 0
        for (conversation_id,) in conversations:
            first_message = db.fetch_val(
                """
                SELECT content
                FROM llmweb_messages
                WHERE conversation_id = %(conversation_id)s
                AND role = 'user'
                ORDER BY message_id
                LIMIT 1
                """,
                dict(conversation_id=conversation_id),
            )

            if not first_message:
                LOG.warning(
                    "No user message found for conversation %s", conversation_id
                )
                continue

            if len(first_message) > 500:
                first_message = first_message[:500] + "..."

            try:
                title = summarize_title(first_message)
                LOG.info(
                    "Generated title %r for conversation %s", title, conversation_id
                )

                db.execute(
                    """
                    UPDATE llmweb_conversations
                    SET title = %(title)s
                    WHERE conversation_id = %(conversation_id)s
                    """,
                    dict(conversation_id=conversation_id, title=title),
                )
                processed += 1
            except Exception:
                LOG.exception(
                    "Failed to generate title for converation %s", conversation_id
                )

        LOG.info(f"Processed {processed} conversations")
