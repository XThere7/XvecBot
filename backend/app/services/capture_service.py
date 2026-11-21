"""
services/capture_service.py
Data Collection and Custom Forms.

Data collections store structured submissions against an agent. Custom forms are
public, token-addressed versions of the same field schema: the token is an
opaque secret, the public API exposes only the form definition and accepts a
validated submission. Neither path ever exposes another tenant's rows.
"""
from __future__ import annotations

import csv
import io
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

from ..models.engagement import (
    CustomFormCreate,
    CustomFormUpdate,
    DataCollectionCreate,
    DataCollectionUpdate,
)
from .field_schema import normalise_fields, validate_submission

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row_to_collection(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["fields"] = _json_load(data.get("fields"), [])
    data["submission_count"] = int(data.get("submission_count") or 0)
    return data


def _row_to_form(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["fields"] = _json_load(data.get("fields"), [])
    data["submission_count"] = int(data.get("submission_count") or 0)
    return data


def _row_to_submission(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["data"] = _json_load(data.get("data"), {})
    return data


def _clean_fields(fields: Any) -> list[dict[str, Any]]:
    try:
        return normalise_fields(fields or [])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


# ── Collections ──────────────────────────────────────────────────────────────


async def list_collections(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    clause = " AND c.is_active = 1" if active_only else ""
    async with db.execute(
        f"""SELECT c.*,
                   (SELECT COUNT(*) FROM data_submissions s
                    WHERE s.collection_id = c.id) AS submission_count
            FROM data_collections c
            WHERE c.workspace_id = ? AND c.agent_id = ?{clause}
            ORDER BY c.created_at DESC""",
        (workspace_id, agent_id),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_collection(r) for r in rows]


async def get_collection(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, collection_id: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM data_submissions s
                   WHERE s.collection_id = c.id) AS submission_count
           FROM data_collections c
           WHERE c.id = ? AND c.workspace_id = ? AND c.agent_id = ?""",
        (collection_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_collection(row) if row is not None else None


async def create_collection(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    payload: DataCollectionCreate,
) -> dict[str, Any]:
    fields = _clean_fields(payload.fields)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add at least one field to the collection.",
        )
    collection_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO data_collections
           (id, workspace_id, agent_id, name, description, instructions, fields,
            is_active, allow_partial, require_consent, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            collection_id,
            workspace_id,
            agent_id,
            payload.name.strip(),
            (payload.description or "").strip() or None,
            (payload.instructions or "").strip() or None,
            json.dumps(fields),
            1 if payload.is_active else 0,
            1 if payload.allow_partial else 0,
            1 if payload.require_consent else 0,
            now,
            now,
        ),
    )
    await db.commit()
    collection = await get_collection(db, workspace_id, agent_id, collection_id)
    assert collection is not None
    return collection


async def update_collection(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    collection_id: str,
    payload: DataCollectionUpdate,
) -> dict[str, Any]:
    existing = await get_collection(db, workspace_id, agent_id, collection_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    updates = payload.model_dump(exclude_unset=True)
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in updates.items():
        if key == "fields":
            fields = _clean_fields(value)
            if not fields:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Add at least one field to the collection.",
                )
            assignments.append("fields = ?")
            values.append(json.dumps(fields))
        elif key in ("is_active", "allow_partial", "require_consent"):
            assignments.append(f"{key} = ?")
            values.append(1 if value else 0)
        elif key in ("name", "description", "instructions"):
            assignments.append(f"{key} = ?")
            values.append((str(value).strip() or None) if value is not None else None)
    if assignments:
        assignments.append("updated_at = ?")
        values.extend([_now(), collection_id, workspace_id, agent_id])
        await db.execute(
            f"""UPDATE data_collections SET {', '.join(assignments)}
                WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            tuple(values),
        )
        await db.commit()
    updated = await get_collection(db, workspace_id, agent_id, collection_id)
    assert updated is not None
    return updated


async def delete_collection(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, collection_id: str
) -> None:
    await db.execute(
        """DELETE FROM data_collections
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (collection_id, workspace_id, agent_id),
    )
    await db.commit()


async def ensure_default_collection(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reuse (or create) the hidden collection used by inline action fields."""
    async with db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM data_submissions s
                   WHERE s.collection_id = c.id) AS submission_count
           FROM data_collections c
           WHERE c.workspace_id = ? AND c.agent_id = ?
           ORDER BY c.created_at ASC LIMIT 1""",
        (workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is not None:
        return _row_to_collection(row)
    return await create_collection(
        db,
        workspace_id,
        agent_id,
        DataCollectionCreate(
            name="Conversation data",
            description="Answers collected by this agent during conversations.",
            fields=fields,
            allow_partial=True,
        ),
    )


# ── Submissions ──────────────────────────────────────────────────────────────


async def create_submission(
    db: aiosqlite.Connection,
    *,
    workspace: dict,
    agent_id: str,
    collection_id: Optional[str],
    conversation_id: Optional[str],
    data: dict[str, Any],
    status: str = "complete",
    inline_fields: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    if collection_id is None:
        collection = await ensure_default_collection(
            db, workspace["id"], agent_id, inline_fields or []
        )
        collection_id = collection["id"]
    submission_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO data_submissions
           (id, workspace_id, agent_id, collection_id, conversation_id, data,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            submission_id,
            workspace["id"],
            agent_id,
            collection_id,
            conversation_id,
            json.dumps(data),
            status,
            now,
        ),
    )
    await db.commit()
    return await get_submission(db, workspace["id"], agent_id, submission_id)


async def get_submission(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, submission_id: str
) -> dict[str, Any]:
    async with db.execute(
        """SELECT * FROM data_submissions
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (submission_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return _row_to_submission(row)


async def list_submissions(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    collection_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    clauses = ["workspace_id = ?", "agent_id = ?"]
    params: list[Any] = [workspace_id, agent_id]
    if collection_id:
        clauses.append("collection_id = ?")
        params.append(collection_id)
    where = " AND ".join(clauses)
    async with db.execute(
        f"SELECT COUNT(*) AS n FROM data_submissions WHERE {where}", tuple(params)
    ) as cur:
        row = await cur.fetchone()
    total = int(row["n"] if row is not None else 0)
    async with db.execute(
        f"""SELECT * FROM data_submissions WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_submission(r) for r in rows], total


async def delete_submission(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, submission_id: str
) -> None:
    await db.execute(
        """DELETE FROM data_submissions
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (submission_id, workspace_id, agent_id),
    )
    await db.commit()


# ── Custom forms ─────────────────────────────────────────────────────────────


async def list_forms(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    clause = " AND f.is_active = 1" if active_only else ""
    async with db.execute(
        f"""SELECT f.*,
                   (SELECT COUNT(*) FROM form_submissions s
                    WHERE s.form_id = f.id) AS submission_count
            FROM custom_forms f
            WHERE f.workspace_id = ? AND f.agent_id = ?{clause}
            ORDER BY f.created_at DESC""",
        (workspace_id, agent_id),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_form(r) for r in rows]


async def get_form(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, form_id: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT f.*,
                  (SELECT COUNT(*) FROM form_submissions s
                   WHERE s.form_id = f.id) AS submission_count
           FROM custom_forms f
           WHERE f.id = ? AND f.workspace_id = ? AND f.agent_id = ?""",
        (form_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_form(row) if row is not None else None


async def get_form_by_token(
    db: aiosqlite.Connection, token: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM custom_forms WHERE public_token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_form(row) if row is not None else None


async def create_form(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    payload: CustomFormCreate,
) -> dict[str, Any]:
    fields = _clean_fields(payload.fields)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add at least one field to the form.",
        )
    form_id = str(uuid.uuid4())
    now = _now()
    token = secrets.token_urlsafe(24)
    await db.execute(
        """INSERT INTO custom_forms
           (id, workspace_id, agent_id, title, description, fields, submit_label,
            is_active, require_consent, public_token, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            form_id,
            workspace_id,
            agent_id,
            payload.title.strip(),
            (payload.description or "").strip() or None,
            json.dumps(fields),
            (payload.submit_label or "Submit").strip()[:60] or "Submit",
            1 if payload.is_active else 0,
            1 if payload.require_consent else 0,
            token,
            now,
            now,
        ),
    )
    await db.commit()
    form = await get_form(db, workspace_id, agent_id, form_id)
    assert form is not None
    return form


async def update_form(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    form_id: str,
    payload: CustomFormUpdate,
) -> dict[str, Any]:
    existing = await get_form(db, workspace_id, agent_id, form_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Form not found"
        )
    updates = payload.model_dump(exclude_unset=True)
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in updates.items():
        if key == "fields":
            fields = _clean_fields(value)
            if not fields:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Add at least one field to the form.",
                )
            assignments.append("fields = ?")
            values.append(json.dumps(fields))
        elif key in ("is_active", "require_consent"):
            assignments.append(f"{key} = ?")
            values.append(1 if value else 0)
        elif key in ("title", "description", "submit_label"):
            assignments.append(f"{key} = ?")
            values.append((str(value).strip() or None) if value is not None else None)
    if assignments:
        assignments.append("updated_at = ?")
        values.extend([_now(), form_id, workspace_id, agent_id])
        await db.execute(
            f"""UPDATE custom_forms SET {', '.join(assignments)}
                WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            tuple(values),
        )
        await db.commit()
    updated = await get_form(db, workspace_id, agent_id, form_id)
    assert updated is not None
    return updated


async def delete_form(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, form_id: str
) -> None:
    await db.execute(
        """DELETE FROM custom_forms
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (form_id, workspace_id, agent_id),
    )
    await db.commit()


async def submit_public_form(
    db: aiosqlite.Connection, token: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate and store one public submission. Returns a sanitised result."""
    form = await get_form_by_token(db, token)
    if form is None or not form.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Form not found"
        )
    cleaned, missing, errors = validate_submission(
        form["fields"],
        data,
        allow_partial=False,
        require_consent=bool(form.get("require_consent")),
    )
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Please check the form.", "errors": errors},
        )
    submission_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO form_submissions
           (id, workspace_id, agent_id, form_id, conversation_id, data, status,
            created_at)
           VALUES (?, ?, ?, ?, NULL, ?, 'complete', ?)""",
        (
            submission_id,
            form["workspace_id"],
            form["agent_id"],
            form["id"],
            json.dumps(cleaned),
            now,
        ),
    )
    await db.commit()
    # Public response deliberately omits workspace/agent ids.
    return {
        "id": submission_id,
        "status": "complete",
        "created_at": now,
        "message": "Thank you — your response has been saved.",
    }


async def list_form_submissions(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    form_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    clauses = ["workspace_id = ?", "agent_id = ?"]
    params: list[Any] = [workspace_id, agent_id]
    if form_id:
        clauses.append("form_id = ?")
        params.append(form_id)
    where = " AND ".join(clauses)
    async with db.execute(
        f"SELECT COUNT(*) AS n FROM form_submissions WHERE {where}", tuple(params)
    ) as cur:
        row = await cur.fetchone()
    total = int(row["n"] if row is not None else 0)
    async with db.execute(
        f"""SELECT * FROM form_submissions WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_submission(r) for r in rows], total


async def delete_form_submission(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, submission_id: str
) -> None:
    await db.execute(
        """DELETE FROM form_submissions
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (submission_id, workspace_id, agent_id),
    )
    await db.commit()


# ── CSV ──────────────────────────────────────────────────────────────────────


def _csv_for_rows(
    fields: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> str:
    keys = [field["key"] for field in fields]
    labels = [field["label"] for field in fields]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", *labels, "status", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row["id"],
                *[row.get("data", {}).get(key, "") for key in keys],
                row.get("status", ""),
                row.get("created_at", ""),
            ]
        )
    return buffer.getvalue()


async def export_collection_csv(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, collection_id: str
) -> str:
    collection = await get_collection(db, workspace_id, agent_id, collection_id)
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    async with db.execute(
        """SELECT * FROM data_submissions
           WHERE workspace_id = ? AND agent_id = ? AND collection_id = ?
           ORDER BY created_at DESC""",
        (workspace_id, agent_id, collection_id),
    ) as cur:
        rows = [_row_to_submission(r) for r in await cur.fetchall()]
    return _csv_for_rows(collection["fields"], rows)


async def export_form_csv(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, form_id: str
) -> str:
    form = await get_form(db, workspace_id, agent_id, form_id)
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Form not found"
        )
    async with db.execute(
        """SELECT * FROM form_submissions
           WHERE workspace_id = ? AND agent_id = ? AND form_id = ?
           ORDER BY created_at DESC""",
        (workspace_id, agent_id, form_id),
    ) as cur:
        rows = [_row_to_submission(r) for r in await cur.fetchall()]
    return _csv_for_rows(form["fields"], rows)
