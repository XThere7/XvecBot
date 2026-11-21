"""
services/support_service.py
Customer Support escalation queue.

When an agent cannot resolve a question — or the visitor explicitly asks for a
human — the action framework creates an escalation. Escalations are tenant
scoped and visible in the agent's Actions → Support panel, where the owner can
move them through open → contacted → closed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

ESCALATION_STATUSES = ("open", "contacted", "closed")
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_escalation(
    db: aiosqlite.Connection,
    *,
    workspace: dict,
    agent_id: str,
    conversation_id: Optional[str],
    reason: str,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
) -> dict[str, Any]:
    escalation_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO support_escalations
           (id, workspace_id, agent_id, conversation_id, reason, contact_name,
            contact_email, contact_phone, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
        (
            escalation_id,
            workspace["id"],
            agent_id,
            conversation_id,
            (reason or "Customer requested human support")[:1000],
            (contact_name or "")[:120] or None,
            (contact_email or "")[:254] or None,
            (contact_phone or "")[:40] or None,
            now,
            now,
        ),
    )
    await db.commit()
    return await get_escalation(db, workspace["id"], agent_id, escalation_id)


async def get_escalation(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, escalation_id: str
) -> dict[str, Any]:
    async with db.execute(
        """SELECT * FROM support_escalations
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (escalation_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found"
        )
    return dict(row)


async def list_escalations(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    status_filter: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    clauses = ["workspace_id = ?", "agent_id = ?"]
    params: list[Any] = [workspace_id, agent_id]
    if status_filter in ESCALATION_STATUSES:
        clauses.append("status = ?")
        params.append(status_filter)
    where = " AND ".join(clauses)
    async with db.execute(
        f"SELECT COUNT(*) AS n FROM support_escalations WHERE {where}",
        tuple(params),
    ) as cur:
        row = await cur.fetchone()
    total = int(row["n"] if row is not None else 0)
    async with db.execute(
        f"""SELECT * FROM support_escalations WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows], total


async def update_status(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    escalation_id: str,
    new_status: str,
) -> dict[str, Any]:
    if new_status not in ESCALATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown escalation status.",
        )
    await get_escalation(db, workspace_id, agent_id, escalation_id)
    await db.execute(
        """UPDATE support_escalations
           SET status = ?, updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (new_status, _now(), escalation_id, workspace_id, agent_id),
    )
    await db.commit()
    return await get_escalation(db, workspace_id, agent_id, escalation_id)


async def stats(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> dict[str, int]:
    async with db.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open,
             SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) AS contacted,
             SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed
           FROM support_escalations
           WHERE workspace_id = ? AND agent_id = ?""",
        (workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return {"total": 0, "open": 0, "contacted": 0, "closed": 0}
    return {
        "total": int(row["total"] or 0),
        "open": int(row["open"] or 0),
        "contacted": int(row["contacted"] or 0),
        "closed": int(row["closed"] or 0),
    }
