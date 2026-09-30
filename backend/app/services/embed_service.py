"""
services/embed_service.py
Public widget chat flow — no JWT required.

Resolves an opaque embed token to an agent, enforces origin allow-listing and
message validation, then delegates to the Phase 3 agent chat pipeline.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import aiosqlite
from fastapi import HTTPException, status

from ..core.logging import get_logger
from .agent_chat_service import chat_with_agent

log = get_logger(__name__)

MAX_MESSAGE_LENGTH = 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hostname(origin: Optional[str]) -> Optional[str]:
    """Extract the hostname from an Origin header (strips protocol + path)."""
    if not origin:
        return None
    try:
        return urlparse(origin).hostname
    except (ValueError, AttributeError):
        return None


def _parse_allowed_origins(raw: Optional[str]) -> Optional[list[str]]:
    """
    Parse the allowed_origins JSON array.
    Returns None when the token allows all origins (NULL / empty / unparsable).
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    return [str(o).lower() for o in parsed]


async def _get_token_row(db: aiosqlite.Connection, token: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM agent_embed_tokens WHERE token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


async def resolve_token(db: aiosqlite.Connection, token: str) -> dict:
    """
    Resolve an embed token to its agent.

    Raises 401 if the token is unknown, 403 if it is revoked or its agent is
    unavailable. Updates last_used_at / request_count fire-and-forget.
    Returns the agent dict.
    """
    embed = await _get_token_row(db, token)
    if embed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid embed token.",
        )

    if not embed["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This embed token has been revoked.",
        )

    async with db.execute(
        "SELECT * FROM agents WHERE id = ?", (embed["agent_id"],)
    ) as cur:
        agent_row = await cur.fetchone()
    if agent_row is None or not agent_row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent is not available.",
        )

    # Fire-and-forget usage tracking — must never block the chat response.
    try:
        await db.execute(
            """UPDATE agent_embed_tokens
               SET last_used_at = ?, request_count = request_count + 1
               WHERE id = ?""",
            (_now(), embed["id"]),
        )
        await db.commit()
    except Exception as exc:
        log.warning("Embed token usage update failed", error=str(exc))

    return dict(agent_row)


async def public_chat(
    db: aiosqlite.Connection,
    token: str,
    message: str,
    conversation_id: Optional[str],
    origin: Optional[str],
) -> dict:
    """
    Handle a public widget chat message.

    Returns the chat_with_agent result (answer, sources, conversation_id,
    model_used).
    """
    agent = await resolve_token(db, token)

    # Origin allow-listing — only enforced when the token restricts origins.
    embed = await _get_token_row(db, token)
    allowed = _parse_allowed_origins(embed.get("allowed_origins") if embed else None)
    if allowed:
        host = _hostname(origin)
        if host is None or host.lower() not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origin not allowed.",
            )

    # Message validation
    cleaned = (message or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message must not be empty.",
        )
    if len(cleaned) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Message must be at most {MAX_MESSAGE_LENGTH} characters.",
        )

    return await chat_with_agent(
        agent_id=agent["id"],
        conversation_id=conversation_id,
        message=cleaned,
        db=db,
    )
