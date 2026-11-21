"""
services/lead_service.py
Sales & Lead Generation: tenant-scoped lead storage, deduplication, filtering
and CSV export.

A lead is never keyed only by an id supplied by a caller. It is always scoped by
``workspace_id`` and ``agent_id``; every read/write in this module includes both
in the WHERE clause. Duplicate submissions from the same email/phone update the
existing lead instead of creating noise.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

from . import action_service
from .field_schema import normalise_fields

LEAD_STATUSES = ("complete", "partial")
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_lead(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["custom_fields"] = action_service._json_load(data.get("custom_fields"), {})
    return data


def _split_lead_fields(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical: dict[str, Any] = {}
    custom: dict[str, Any] = {}
    for key, value in data.items():
        if key in action_service.LEAD_COLUMNS:
            canonical[key] = value
        else:
            custom[key] = value
    return canonical, custom


async def upsert_lead(
    db: aiosqlite.Connection,
    *,
    workspace: dict,
    agent_id: str,
    action_id: Optional[str],
    conversation_id: Optional[str],
    data: dict[str, Any],
    status: str = "complete",
    consent_given: bool = False,
    consent_text: Optional[str] = None,
) -> dict[str, Any]:
    """Insert a lead or merge it into the matching email/phone lead."""
    if status not in LEAD_STATUSES:
        status = "complete"
    canonical, custom = _split_lead_fields(data)
    dedupe_key = action_service.dedupe_key_for({**canonical, **custom}, conversation_id)

    async with db.execute(
        """SELECT * FROM leads
           WHERE workspace_id = ? AND agent_id = ? AND dedupe_key = ?""",
        (workspace["id"], agent_id, dedupe_key),
    ) as cur:
        existing = await cur.fetchone()

    now = _now()
    if existing is not None:
        existing_data = _row_to_lead(existing)
        merged_custom = {**existing_data.get("custom_fields", {}), **custom}
        # Never blank out a value the visitor already gave us.
        merged_canonical = {
            key: canonical.get(key) or existing_data.get(key)
            for key in action_service.LEAD_COLUMNS
        }
        merged_status = "complete" if status == "complete" or existing_data["status"] == "complete" else "partial"
        await db.execute(
            """UPDATE leads
               SET action_id = COALESCE(?, action_id),
                   conversation_id = COALESCE(?, conversation_id),
                   full_name = ?, email = ?, phone = ?, company = ?,
                   interest = ?, budget = ?, notes = ?, custom_fields = ?,
                   status = ?, consent_given = ?, consent_text = COALESCE(?, consent_text),
                   updated_at = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (
                action_id,
                conversation_id,
                merged_canonical.get("full_name"),
                merged_canonical.get("email"),
                merged_canonical.get("phone"),
                merged_canonical.get("company"),
                merged_canonical.get("interest"),
                merged_canonical.get("budget"),
                merged_canonical.get("notes"),
                json.dumps(merged_custom),
                merged_status,
                1 if (consent_given or existing_data.get("consent_given")) else 0,
                consent_text,
                now,
                existing_data["id"],
                workspace["id"],
                agent_id,
            ),
        )
        await db.commit()
        lead_id = existing_data["id"]
    else:
        lead_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO leads
               (id, workspace_id, agent_id, action_id, conversation_id,
                full_name, email, phone, company, interest, budget, notes,
                custom_fields, status, consent_given, consent_text, dedupe_key,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_id,
                workspace["id"],
                agent_id,
                action_id,
                conversation_id,
                canonical.get("full_name"),
                canonical.get("email"),
                canonical.get("phone"),
                canonical.get("company"),
                canonical.get("interest"),
                canonical.get("budget"),
                canonical.get("notes"),
                json.dumps(custom),
                status,
                1 if consent_given else 0,
                consent_text,
                dedupe_key,
                now,
                now,
            ),
        )
        await db.commit()

    return await get_lead(db, workspace["id"], agent_id, lead_id)


async def get_lead(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, lead_id: str
) -> dict[str, Any]:
    async with db.execute(
        """SELECT * FROM leads
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (lead_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )
    return _row_to_lead(row)


async def list_leads(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    clauses = ["workspace_id = ?", "agent_id = ?"]
    params: list[Any] = [workspace_id, agent_id]
    if status_filter in LEAD_STATUSES:
        clauses.append("status = ?")
        params.append(status_filter)
    if search and search.strip():
        term = f"%{search.strip()[:100]}%"
        clauses.append(
            "(full_name LIKE ? OR email LIKE ? OR phone LIKE ? OR company LIKE ? OR interest LIKE ?)"
        )
        params.extend([term] * 5)
    where = " AND ".join(clauses)

    async with db.execute(
        f"SELECT COUNT(*) AS n FROM leads WHERE {where}", tuple(params)
    ) as cur:
        count_row = await cur.fetchone()
    total = int(count_row["n"] if count_row is not None else 0)

    async with db.execute(
        f"""SELECT * FROM leads WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_lead(r) for r in rows], total


async def delete_lead(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, lead_id: str
) -> None:
    await db.execute(
        """DELETE FROM leads
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (lead_id, workspace_id, agent_id),
    )
    await db.commit()


async def export_leads_csv(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> str:
    """Every lead for one agent as CSV (canonical columns + custom field keys)."""
    async with db.execute(
        """SELECT * FROM leads
           WHERE workspace_id = ? AND agent_id = ?
           ORDER BY created_at DESC""",
        (workspace_id, agent_id),
    ) as cur:
        rows = [_row_to_lead(r) for r in await cur.fetchall()]

    custom_keys: list[str] = []
    for row in rows:
        for key in row.get("custom_fields", {}):
            if key not in custom_keys:
                custom_keys.append(key)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            *action_service.LEAD_COLUMNS,
            *custom_keys,
            "status",
            "consent_given",
            "conversation_id",
            "created_at",
            "updated_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                *[row.get(key) or "" for key in action_service.LEAD_COLUMNS],
                *[row.get("custom_fields", {}).get(key, "") for key in custom_keys],
                row["status"],
                row["consent_given"],
                row.get("conversation_id") or "",
                row["created_at"],
                row["updated_at"],
            ]
        )
    return buffer.getvalue()


async def lead_stats(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    async with db.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS complete,
             SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) AS partial,
             SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS last_7_days
           FROM leads WHERE workspace_id = ? AND agent_id = ?""",
        (cutoff, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return {"total": 0, "complete": 0, "partial": 0, "last_7_days": 0}
    return {
        "total": int(row["total"] or 0),
        "complete": int(row["complete"] or 0),
        "partial": int(row["partial"] or 0),
        "last_7_days": int(row["last_7_days"] or 0),
    }
