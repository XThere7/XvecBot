"""
services/conversation_service.py
Business logic for agent conversation history.

Manages the shared `conversations` and `messages` tables (Phase 1 + Phase 3).
Agent conversations are rows with a non-NULL agent_id; legacy Phase 1 rows have
agent_id NULL and are untouched by this service.

Sources are stored in the existing `citations` JSON column and exposed to callers
as a parsed Python list under the key `sources`.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from ..core.logging import get_logger

log = get_logger(__name__)

DEFAULT_TITLE = "New Conversation"
MAX_TITLE_LENGTH = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sources(raw) -> list:
    """Parse the stored citations JSON string back into a list."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        log.warning("Could not parse message sources", raw=str(raw)[:100])
        return []


def _message_to_dict(row) -> dict:
    """Convert a messages row into the API shape (sources as a list)."""
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "sources": _parse_sources(row["citations"]),
        "created_at": row["created_at"],
    }


async def create_conversation(
    db: aiosqlite.Connection,
    agent_id: str,
    title: Optional[str] = None,
) -> dict:
    """Create a conversation for an agent. Defaults the title if none is given."""
    conversation_id = str(uuid.uuid4())
    now = _now()
    final_title = title if title else DEFAULT_TITLE
    await db.execute(
        """INSERT INTO conversations (id, agent_id, title, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, agent_id, final_title, now, now),
    )
    await db.commit()
    return await get_conversation(db, conversation_id)


async def get_conversations_for_agent(
    db: aiosqlite.Connection,
    agent_id: str,
) -> list[dict]:
    """All conversations for an agent, most recently updated first."""
    async with db.execute(
        "SELECT * FROM conversations WHERE agent_id = ? ORDER BY updated_at DESC",
        (agent_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> Optional[dict]:
    """Fetch one conversation by id, or None if it does not exist."""
    async with db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


async def get_conversation_messages(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> list[dict]:
    """All messages for a conversation, oldest first, sources parsed to lists."""
    async with db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_message_to_dict(r) for r in rows]


async def add_message(
    db: aiosqlite.Connection,
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[list] = None,
) -> dict:
    """
    Append a message to a conversation and bump the conversation's updated_at.

    `sources` is a list of citation dicts, serialised to JSON and stored in the
    shared `citations` column. Returns the message with `sources` as a list.
    """
    if role not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")

    message_id = str(uuid.uuid4())
    now = _now()
    sources_json = json.dumps(sources) if sources is not None else None

    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, citations, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (message_id, conversation_id, role, content, sources_json, now),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    await db.commit()

    async with db.execute(
        "SELECT * FROM messages WHERE id = ?", (message_id,)
    ) as cur:
        row = await cur.fetchone()
    return _message_to_dict(row)


async def build_history_for_llm(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> list[dict]:
    """
    Message history in the shape the LLM expects: only role and content.
    Strips id, sources and created_at so nothing extra reaches the prompt.
    """
    messages = await get_conversation_messages(db, conversation_id)
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def _make_title(first_user_message: str) -> str:
    """Shorten the first user message into a conversation title."""
    text = first_user_message.strip()
    if len(text) <= MAX_TITLE_LENGTH:
        return text
    truncated = text[:MAX_TITLE_LENGTH]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.strip()


async def auto_title_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
    first_user_message: str,
) -> None:
    """
    Replace the default title with one derived from the first user message.

    Best-effort: never raises. Only renames conversations still titled
    "New Conversation".
    """
    try:
        conversation = await get_conversation(db, conversation_id)
        if conversation is None:
            return
        if conversation["title"] != DEFAULT_TITLE:
            return
        title = _make_title(first_user_message)
        if not title:
            return
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conversation_id),
        )
        await db.commit()
        log.info(
            "Conversation auto-titled",
            conversation_id=conversation_id,
            title=title,
        )
    except Exception as exc:
        log.warning(
            "auto_title_conversation failed",
            conversation_id=conversation_id,
            error=str(exc),
        )


async def delete_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> None:
    """Delete every message in a conversation, then the conversation itself."""
    await db.execute(
        "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
    )
    await db.execute(
        "DELETE FROM conversations WHERE id = ?", (conversation_id,)
    )
    await db.commit()
    log.info("Conversation deleted", conversation_id=conversation_id)
