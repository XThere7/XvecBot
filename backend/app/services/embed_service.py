"""
services/embed_service.py
Public widget chat flow — no JWT required.

Resolves an opaque embed token to an agent, enforces origin allow-listing and
message validation, then delegates to the Phase 3 agent chat pipeline.
"""
import json
import re
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

# Hostnames that are always permitted even when a token restricts origins, so a
# merchant can develop against http://localhost:3000 without loosening the list.
LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

# Control characters stripped from visitor input. Tab (\t) and newline (\n) are
# kept because visitors legitimately paste multi-line questions.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hostname(origin: Optional[str]) -> Optional[str]:
    """
    Extract a comparable hostname from an Origin header.

        "https://mystore.co.tz"   -> "mystore.co.tz"
        "https://www.mystore..."  -> "www.mystore.co.tz"
        "http://localhost:3000"   -> "localhost"

    Returns None when there is nothing usable to compare against:
      * no header at all (curl, Postman, server-to-server)
      * the literal "null", sent by sandboxed iframes and file:// pages
      * any value that is not a real http(s) origin
    """
    if not origin:
        return None
    candidate = origin.strip()
    if not candidate or candidate.lower() == "null":
        return None
    try:
        parsed = urlparse(candidate)
    except (ValueError, AttributeError):
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    try:
        return (parsed.hostname or "").lower() or None
    except ValueError:
        # urlparse raises on malformed hosts (e.g. an out-of-range port).
        return None


def _normalise_origin_entry(entry: str) -> Optional[str]:
    """
    Normalise one stored allowed_origins entry to a bare, lowercased hostname.

    Owners may save any of these and they must all match an incoming Origin:

        "mystore.co.tz"             <- the documented format
        "https://mystore.co.tz"     <- a full URL
        "mystore.co.tz:8443"        <- with an explicit port

    Ports and schemes are discarded because the browser's Origin is compared on
    hostname alone. A stored "null" (or anything unparseable) yields None so it
    is dropped from the list rather than silently matching nothing.
    """
    if not isinstance(entry, str):
        return None
    candidate = entry.strip().lower()
    if not candidate or candidate == "null":
        return None
    # A bare hostname has no scheme, so urlparse would return None for it.
    # Prefixing "//" makes urlparse treat the value as a network location.
    target = candidate if "://" in candidate else "//" + candidate
    try:
        parsed = urlparse(target)
        return (parsed.hostname or "").lower() or None
    except ValueError:
        return None


def _parse_allowed_origins(raw: Optional[str]) -> Optional[list[str]]:
    """
    Parse the allowed_origins JSON array into comparable hostnames.
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
    hosts = {h for h in (_normalise_origin_entry(o) for o in parsed) if h}
    return sorted(hosts) or None


def _check_origin(origin: Optional[str], allowed: Optional[list[str]]) -> None:
    """
    Enforce a token's per-widget origin allow-list.

    allowed is None (open mode) -> every origin is permitted.
    allowed is a list (restricted mode) ->
        * a missing Origin header is permitted: direct API calls, curl, Postman
          and server-to-server callers cannot present a browser Origin at all,
          and they already hold the token, so there is nothing to gate.
        * a "null" origin (sandboxed iframe / file://) is refused, because it
          carries no verifiable host.
        * localhost is always permitted for local development.
        * anything else must appear in the list, matched exactly on hostname.
          Note that "mystore.co.tz" and "www.mystore.co.tz" are different hosts,
          so a merchant serving both must list both.
    """
    if not allowed:
        return  # open mode — all origins allowed

    if not origin or not origin.strip():
        return  # no Origin header: direct/non-browser caller

    host = _hostname(origin)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A null or unparseable Origin is not authorised for this widget.",
        )
    if host in LOCALHOST_HOSTS or host in allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Origin {origin} is not authorised for this widget.",
    )


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


def _sanitise_message(message: Optional[str]) -> str:
    """
    Normalise untrusted visitor input before it reaches the LLM or the database.

      * strips leading/trailing whitespace
      * drops NUL bytes and other C0/C1 control characters
      * keeps tab and newline so pasted multi-line questions survive intact
      * collapses Windows/legacy newlines to \\n

    Length is *not* enforced here — public_chat measures the sanitised text so
    the 4000 limit always applies to what is actually stored.
    """
    text = message or ""
    # Normalise CRLF / CR to LF first so the control-character sweep cannot
    # leave a stray CR behind.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    return text.strip()


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
    _check_origin(origin, allowed)

    # Sanitise first, then validate length against the sanitised text.
    cleaned = _sanitise_message(message)
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
