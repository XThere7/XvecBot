"""
services/admin_service.py
Shared helpers for the admin panel: audit trail, pagination/sort validation,
platform settings, plan changes, payments, deletion cascade, and the
fire-and-forget usage/error recorders.

The audit writer is the only code path that inserts into audit_log. Mutating
admin endpoints must call it (including failed/denied sensitive attempts) —
the append-only DB triggers do the rest.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from ..core.config import settings
from ..core.logging import get_logger
from ..core.plan import PLAN_IDS

log = get_logger(__name__)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# ── Audit trail ──────────────────────────────────────────────────────────────
async def write_audit(
    db,
    *,
    actor: dict,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    summary: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert one append-only audit row. Summary must never carry secrets."""
    await db.execute(
        "INSERT INTO audit_log (id, ts, actor_id, actor_email, action, "
        "target_type, target_id, summary, ip, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            datetime.now(timezone.utc).isoformat(),
            actor.get("id"),
            actor.get("email"),
            action,
            target_type,
            target_id,
            summary[:500],
            (ip or "")[:64],
            (user_agent or "")[:200],
        ),
    )


# ── Pagination / sort / search validation ────────────────────────────────────
def page_params(page: int | None, page_size: int | None) -> tuple[int, int]:
    page = max(1, int(page or 1))
    size = max(1, min(MAX_PAGE_SIZE, int(page_size or DEFAULT_PAGE_SIZE)))
    return page, size


def validate_sort(sort: str | None, allowed: set[str], default: str) -> str:
    """Allow-list for ORDER BY — anything else falls back to the default."""
    if sort and sort in allowed:
        return sort
    return default


def validate_direction(direction: str | None) -> str:
    return "DESC" if (direction or "desc").lower() == "desc" else "ASC"


def like_pattern(term: str | None) -> str | None:
    term = (term or "").strip()
    return f"%{term}%" if term else None


# ── Platform settings (5s in-process cache) ──────────────────────────────────
_SETTINGS_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_SETTINGS_TTL = 5.0


async def get_platform_settings(db) -> dict[str, str]:
    cached = _SETTINGS_CACHE.get("v")
    if cached and time.monotonic() - cached[0] < _SETTINGS_TTL:
        return dict(cached[1])
    cur = await db.execute("SELECT key, value FROM platform_settings")
    rows = await cur.fetchall()
    values = {row["key"]: row["value"] for row in rows}
    _SETTINGS_CACHE["v"] = (time.monotonic(), values)
    return values


async def set_platform_setting(db, key: str, value: str, actor_email: str) -> None:
    await db.execute(
        "INSERT INTO platform_settings (key, value, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
        (key, value, datetime.now(timezone.utc).isoformat(), actor_email),
    )
    _SETTINGS_CACHE.pop("v", None)


def clear_platform_settings_cache() -> None:
    _SETTINGS_CACHE.clear()


UNAVAILABLE_DETAIL = "This assistant is temporarily unavailable."


async def platform_emergency_off(db) -> bool:
    """True when the emergency switch disables public + developer surfaces."""
    values = await get_platform_settings(db)
    return values.get("emergency_off") == "true"


async def require_platform_available(db) -> None:
    if await platform_emergency_off(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        )


async def require_owner_active(db, workspace_id: str) -> None:
    """503 when the workspace owner is suspended or deactivated."""
    cur = await db.execute(
        "SELECT u.is_active, u.suspended_at FROM workspaces w "
        "JOIN users u ON u.id = w.owner_id WHERE w.id = ?",
        (workspace_id,),
    )
    row = await cur.fetchone()
    if row is None or not row["is_active"] or row["suspended_at"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        )


async def signups_open(db) -> bool:
    values = await get_platform_settings(db)
    return values.get("signups_open", "true") != "false"


# ── Instrumentation (fire-and-forget) ────────────────────────────────────────
def record_usage_event(*, user_id: str, workspace_id: str, agent_id: str | None,
                       channel: str, model: str, status: str,
                       latency_ms: int | None = None,
                       prompt_tokens: int | None = None,
                       completion_tokens: int | None = None,
                       error_code: str | None = None) -> None:
    """Schedule one usage row off the request path. Never raises."""
    now = datetime.now(timezone.utc)
    row = {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "kind": "chat",
        "quantity": 1,
        "created_at": now.isoformat(),
        "user_id": user_id,
        "agent_id": agent_id,
        "channel": channel,
        "model": model,
        "status": status,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "error_code": error_code,
        "month": now.strftime("%Y-%m"),
    }

    async def _write():
        try:
            from ..core.database import get_db

            async with get_db() as db:
                await db.execute(
                    "INSERT INTO usage_events (id, workspace_id, kind, quantity, "
                    "created_at, user_id, agent_id, channel, model, status, "
                    "latency_ms, prompt_tokens, completion_tokens, error_code, month) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"], row["workspace_id"], row["kind"], row["quantity"],
                        row["created_at"], row["user_id"], row["agent_id"],
                        row["channel"], row["model"], row["status"], row["latency_ms"],
                        row["prompt_tokens"], row["completion_tokens"],
                        row["error_code"], row["month"],
                    ),
                )
                await db.commit()
        except Exception as exc:  # pragma: no cover - best effort
            log.debug("usage event dropped", outcome=type(exc).__name__)

    try:
        asyncio.create_task(_write())
    except RuntimeError:  # no running loop (rare, tests) — run inline
        asyncio.run(_write())


def record_error_event(*, path: str, status: int | None,
                       exception_type: str, message: str) -> None:
    """Schedule one error row off the request path. Never raises."""

    async def _write():
        try:
            from ..core.database import get_db

            async with get_db() as db:
                await db.execute(
                    "INSERT INTO error_events (id, ts, path, status, "
                    "exception_type, message) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        datetime.now(timezone.utc).isoformat(),
                        path[:500],
                        status,
                        exception_type[:120],
                        (message or "")[:300],
                    ),
                )
                await db.commit()
        except Exception as exc:  # pragma: no cover - best effort
            log.debug("error event dropped", outcome=type(exc).__name__)

    try:
        asyncio.create_task(_write())
    except RuntimeError:
        asyncio.run(_write())


async def purge_old_usage_events(db) -> int:
    """Retention: delete usage rows older than the configured window."""
    from datetime import timedelta

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=settings.usage_events_retention_days)
    ).isoformat()
    cur = await db.execute("DELETE FROM usage_events WHERE created_at < ?", (cutoff,))
    await db.commit()
    return cur.rowcount if cur.rowcount else 0


# ── Plan changes / payments ──────────────────────────────────────────────────
async def record_plan_change(db, *, user_id: str, from_plan: str | None,
                             to_plan: str, reason: str, changed_by: str) -> None:
    await db.execute(
        "INSERT INTO plan_changes (id, user_id, from_plan, to_plan, reason, "
        "changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            user_id,
            from_plan,
            to_plan,
            (reason or "")[:500],
            changed_by,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


async def apply_plan_change(db, *, user: dict, to_plan: str, reason: str,
                            actor: dict) -> dict:
    """Change a user's stored plan (no trial mutation) and record history."""
    if to_plan not in PLAN_IDS:
        raise ValueError(f"unknown plan {to_plan!r}")
    from_plan = user.get("plan") or "free"
    await db.execute(
        "UPDATE users SET plan = ? WHERE id = ?", (to_plan, user["id"])
    )
    await record_plan_change(
        db,
        user_id=user["id"],
        from_plan=from_plan,
        to_plan=to_plan,
        reason=reason,
        changed_by=actor.get("email") or actor.get("id") or "system",
    )
    return {"plan": to_plan, "from": from_plan}


async def apply_trial_change(db, *, user: dict, days: int, reason: str,
                             actor: dict) -> dict:
    """Extend (or replace) the trial end from now + days. days<=0 ends it."""
    from datetime import timedelta

    end = (
        datetime.now(timezone.utc) + timedelta(days=int(days))
        if int(days) > 0
        else None
    )
    await db.execute(
        "UPDATE users SET trial_ends_at = ? WHERE id = ?",
        (end.isoformat() if end else None, user["id"]),
    )
    return {"trial_ends_at": end.isoformat() if end else None}


# ── User deletion cascade ────────────────────────────────────────────────────
async def delete_user_cascade(db, user_id: str) -> None:
    """
    Remove a user and every owned row: workspaces (with their documents,
    chunks, vectors, agents, conversations, tokens, keys, website sources),
    usage, reset tokens, payments, plan history. audit_log keeps actor_email
    (append-only) so the trail survives.

    Mirrors the workspace delete endpoint's row order (vectors first, files
    collected before row deletes) so nothing can be orphaned.
    """
    from ..storage import vector_store
    from ..storage.object_store import get_storage

    cur = await db.execute("SELECT id FROM workspaces WHERE owner_id = ?", (user_id,))
    workspaces = await cur.fetchall()

    for row in workspaces:
        workspace_id = row["id"]

        async with db.execute(
            "SELECT * FROM workspace_documents "
            "WHERE workspace_id = ? AND file_type NOT IN ('website', 'social')",
            (workspace_id,),
        ) as cur:
            doc_rows = [dict(r) for r in await cur.fetchall()]

        await vector_store.delete_by_workspace(db, workspace_id)
        await db.execute(
            """DELETE FROM chunks
               WHERE workspace_id = ?
                  OR doc_id IN (SELECT id FROM workspace_documents WHERE workspace_id = ?)
                  OR document_id IN (SELECT id FROM workspace_documents WHERE workspace_id = ?)""",
            (workspace_id, workspace_id, workspace_id),
        )
        await db.execute(
            "DELETE FROM documents WHERE id IN "
            "(SELECT id FROM workspace_documents WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            """DELETE FROM messages
               WHERE conversation_id IN (
                   SELECT id FROM conversations
                   WHERE agent_id IN (SELECT id FROM agents WHERE workspace_id = ?)
               )""",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM conversations WHERE agent_id IN "
            "(SELECT id FROM agents WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM conversations WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM agent_embed_tokens WHERE agent_id IN "
            "(SELECT id FROM agents WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM developer_api_keys WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM usage_events WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_pages WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sync_jobs WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sources WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM social_media_sources WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute("DELETE FROM agents WHERE workspace_id = ?", (workspace_id,))
        await db.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

        # Best-effort byte cleanup outside the transaction-like flow.
        for doc in doc_rows:
            _remove_doc_files(doc)
        try:
            await asyncio.to_thread(
                get_storage().delete_prefix,
                f"workspaces/{workspace_id}",
            )
        except Exception:  # pragma: no cover - best effort
            pass

    await db.execute("DELETE FROM usage_monthly WHERE user_id = ?", (user_id,))
    await db.execute(
        "DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,)
    )
    await db.execute("DELETE FROM plan_changes WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _remove_doc_files(doc: dict) -> None:
    """Best-effort file/object cleanup for one document row."""
    try:
        path = doc.get("file_path")
        if path and Path(path).exists():
            Path(path).unlink(missing_ok=True)
    except Exception:  # pragma: no cover - best effort
        pass
    try:
        from ..storage.object_store import get_storage

        if doc.get("object_key"):
            get_storage().delete_object(doc["object_key"])
    except Exception:  # pragma: no cover - best effort
        pass
