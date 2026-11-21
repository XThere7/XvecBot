"""
services/notification_service.py
Simulated SMS notifications.

There is no SMS gateway configured for this deployment. Messages are stored in
``notification_messages`` with provider/status ``simulated`` and are shown in the
dashboard as exactly that — never as delivered. The interface is deliberately
the same shape a real provider would use, so replacing the sender later only
requires changing this module.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

MAX_BODY_LENGTH = 480
MAX_NOTIFICATIONS = 50

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,24}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_phone(raw: Optional[str]) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not _PHONE_RE.match(text) or not (7 <= len(digits) <= 15):
        return None
    return text


async def send_simulated_sms(
    db: aiosqlite.Connection,
    *,
    workspace_id: str,
    agent_id: str,
    recipient: Optional[str],
    body: str,
    related_type: Optional[str] = None,
    related_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Store one simulated SMS. Returns None when no valid recipient is set."""
    phone = normalise_phone(recipient)
    if phone is None:
        return None
    message_id = str(uuid.uuid4())
    now = _now()
    cleaned = (body or "").strip()[:MAX_BODY_LENGTH]
    await db.execute(
        """INSERT INTO notification_messages
           (id, workspace_id, agent_id, channel, provider, recipient, body,
            status, related_type, related_id, error_message, created_at,
            simulated_at)
           VALUES (?, ?, ?, 'sms', 'simulated', ?, ?, 'simulated', ?, ?, NULL,
                   ?, ?)""",
        (
            message_id,
            workspace_id,
            agent_id,
            phone,
            cleaned,
            related_type,
            related_id,
            now,
            now,
        ),
    )
    await db.commit()
    return await get_notification(db, workspace_id, agent_id, message_id)


async def get_notification(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, message_id: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM notification_messages
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (message_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


async def list_notifications(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> list[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM notification_messages
           WHERE workspace_id = ? AND agent_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (workspace_id, agent_id, MAX_NOTIFICATIONS),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
