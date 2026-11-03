"""
services/plan_service.py
Subscription usage and enforcement.

Design notes
------------
* The account-level plan/trial state lives on `users`; the legacy workspace
  plan is retained as an operator/paid-workspace override. Enforcement uses the
  stronger of the owner's effective plan and the workspace plan, so an active
  trial grants Pro access without erasing an existing paid workspace.
* Usage periods are **calendar months in UTC** (1st 00:00 → next 1st 00:00).
  AI responses remain in the `usage_events` ledger for analytics. Chat messages
  use the account counter in `usage_monthly` and are enforced before the LLM.
* Agents, documents, website sources, indexed pages, API keys and embed tokens
  are derived live from their tables. Deleting a resource frees capacity.
* Plan limits raise HTTP 403 with a structured detail object; the monthly chat
  allowance raises HTTP 429. Storage and legacy social-media gates retain the
  existing 402 contract used by the dashboard.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

from ..core.logging import get_logger
from ..core.plan import (
    PLAN_RANK,
    check_limit_for_plan,
    get_limits_for_plan,
    get_trial_status,
    normalize_plan_id,
    refresh_policy_rank,
    resolve_effective_plan,
)
from ..core.plans import PLAN_CATALOG, Plan, get_plan, plan_list

log = get_logger(__name__)

PAYMENT_NOT_CONFIGURED = (
    "Paid plans are not available yet — payments are not configured. "
    "Every new account includes a 21-day Pro trial, after which it moves to "
    "Free automatically."
)


# ── Periods and formatting ───────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def period_bounds(now: Optional[datetime] = None) -> tuple[str, str]:
    """Return (start, end) ISO strings for the current UTC calendar month."""
    now = now or _utc_now()
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def format_reset_date(iso_value: str) -> str:
    """'2026-11-01T00:00:00+00:00' → '1 November 2026'."""
    try:
        dt = datetime.fromisoformat(iso_value)
    except ValueError:
        return iso_value
    return f"{dt.day} {dt.strftime('%B %Y')}"


def format_bytes(value: int) -> str:
    """Human storage size for limit messages ('100 MB', '1.5 GB')."""
    if value >= 1024**3:
        amount = value / 1024**3
        unit = "GB"
    elif value >= 1024**2:
        amount = value / 1024**2
        unit = "MB"
    elif value >= 1024:
        amount = value / 1024
        unit = "KB"
    else:
        return f"{value} B"
    text = f"{amount:.1f}".rstrip("0").rstrip(".")
    return f"{text} {unit}"


# ── Workspace, user and effective-plan resolution ───────────────────────────


async def get_workspace(db: aiosqlite.Connection, workspace_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


async def get_user(db: aiosqlite.Connection, user_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


def _workspace_plan_id(workspace: dict) -> str:
    return normalize_plan_id(workspace.get("plan"))


async def resolve_plan(
    db: aiosqlite.Connection, workspace: dict
) -> tuple[Plan, Optional[dict], str]:
    """
    Resolve the plan used for a workspace.

    Returns ``(plan, owner_user, effective_id)`` where effective_id is one of
    ``free|standard|pro|trial``. A trial behaves as Pro. A paid workspace plan
    is preserved if it is stronger than the owner's account plan.
    """
    owner = await get_user(db, workspace.get("owner_id"))
    user_effective = resolve_effective_plan(owner) if owner else "free"
    workspace_plan = _workspace_plan_id(workspace)
    effective_id = (
        user_effective
        if PLAN_RANK[user_effective] >= PLAN_RANK[workspace_plan]
        else workspace_plan
    )
    # Trial and Pro have identical limits; the catalogue has no purchasable
    # trial tier, so expose Pro while retaining the effective trial id.
    catalogue_id = "pro" if effective_id == "trial" else effective_id
    return get_plan(catalogue_id), owner, effective_id


async def plan_for_workspace(
    db: aiosqlite.Connection, workspace: dict
) -> Plan:
    """Backwards-compatible async resolver used by services and billing."""
    plan, _, _ = await resolve_plan(db, workspace)
    return plan


async def effective_plan_id(
    db: aiosqlite.Connection, workspace: dict
) -> str:
    _, _, effective_id = await resolve_plan(db, workspace)
    return effective_id


# ── Counters ────────────────────────────────────────────────────────────────


async def count_agents(db: aiosqlite.Connection, workspace_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) AS n FROM agents WHERE workspace_id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def count_documents(db: aiosqlite.Connection, workspace_id: str) -> int:
    """Uploaded documents only; website pages and social imports are excluded."""
    async with db.execute(
        """SELECT COUNT(*) AS n FROM workspace_documents
           WHERE workspace_id = ? AND file_type NOT IN ('website', 'social')""",
        (workspace_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def count_website_sources(
    db: aiosqlite.Connection, workspace_id: str
) -> int:
    async with db.execute(
        "SELECT COUNT(*) AS n FROM website_sources WHERE workspace_id = ?",
        (workspace_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def pages_indexed_used(
    db: aiosqlite.Connection, workspace_id: str
) -> int:
    async with db.execute(
        """SELECT COUNT(*) AS n FROM website_pages
           WHERE workspace_id = ? AND status = 'indexed'""",
        (workspace_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def count_api_keys(db: aiosqlite.Connection, workspace_id: str) -> int:
    """Active keys count against the quota; revoked keys free the slot."""
    async with db.execute(
        """SELECT COUNT(*) AS n FROM developer_api_keys
           WHERE workspace_id = ? AND is_active = 1""",
        (workspace_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def count_embed_tokens(
    db: aiosqlite.Connection, agent_id: str
) -> int:
    async with db.execute(
        """SELECT COUNT(*) AS n FROM agent_embed_tokens
           WHERE agent_id = ? AND is_active = 1""",
        (agent_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def count_embed_tokens_for_workspace(
    db: aiosqlite.Connection, workspace_id: str
) -> int:
    async with db.execute(
        """SELECT COUNT(*) AS n
           FROM agent_embed_tokens t
           JOIN agents a ON a.id = t.agent_id
           WHERE a.workspace_id = ? AND t.is_active = 1""",
        (workspace_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def chat_messages_used(
    db: aiosqlite.Connection, user_id: str, month: Optional[str] = None
) -> int:
    month = month or _utc_now().strftime("%Y-%m")
    async with db.execute(
        "SELECT chat_messages FROM usage_monthly WHERE user_id = ? AND month = ?",
        (user_id, month),
    ) as cur:
        row = await cur.fetchone()
    return int(row["chat_messages"] if row is not None else 0)


async def storage_used_bytes(
    db: aiosqlite.Connection,
    workspace_id: str,
    exclude_doc_id: Optional[str] = None,
) -> int:
    """Knowledge-base bytes for a workspace (sum of uploaded document sizes)."""
    if exclude_doc_id:
        query = (
            "SELECT COALESCE(SUM(size_bytes), 0) AS total "
            "FROM workspace_documents WHERE workspace_id = ? AND id <> ?"
        )
        params = (workspace_id, exclude_doc_id)
    else:
        query = (
            "SELECT COALESCE(SUM(size_bytes), 0) AS total "
            "FROM workspace_documents WHERE workspace_id = ?"
        )
        params = (workspace_id,)
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return int(row["total"] if row is not None else 0)


async def social_media_sources_used(
    db: aiosqlite.Connection, agent_id: str
) -> int:
    """Count every non-deleted social media source for one agent."""
    async with db.execute(
        "SELECT COUNT(*) AS n FROM social_media_sources WHERE agent_id = ?",
        (agent_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"] if row is not None else 0)


async def responses_used(
    db: aiosqlite.Connection,
    workspace_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> int:
    """AI responses recorded in the current (or supplied) UTC month."""
    if start is None or end is None:
        start, end = period_bounds()
    async with db.execute(
        """SELECT COALESCE(SUM(quantity), 0) AS total
           FROM usage_events
           WHERE workspace_id = ? AND kind = 'ai_response'
             AND created_at >= ? AND created_at < ?""",
        (workspace_id, start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["total"] if row is not None else 0)


# ── Structured limit errors ─────────────────────────────────────────────────


def limit_error(
    *,
    resource: str,
    plan: Plan,
    used: int | str,
    limit: int | str,
    message: str,
    resets_at: Optional[str] = None,
    code: str = "plan_limit_reached",
    status_code: int = status.HTTP_403_FORBIDDEN,
    plan_id: Optional[str] = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "resource": resource,
            "message": message,
            "plan": plan_id or plan.id,
            "plan_name": plan.name,
            "used": used,
            "limit": limit,
            "resets_at": resets_at,
            "upgrade_required": True,
            "payments_configured": False,
        },
    )


def _limit_reason(plan_id: str, resource: str, limit: Any) -> str:
    pretty_plan = plan_id.capitalize() if plan_id != "trial" else "trial"
    return (
        f"Your {pretty_plan} plan allows a maximum of {limit} {resource}. "
        "Upgrade to Standard or Pro to add more."
    )


# ── Creation gates ──────────────────────────────────────────────────────────


async def assert_can_create_agent(
    db: aiosqlite.Connection, workspace: dict
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    used = await count_agents(db, workspace["id"])
    allowed, reason = check_limit_for_plan(effective_id, "agents", used)
    if not allowed:
        limit = get_limits_for_plan(effective_id)["agents"]
        raise limit_error(
            resource="agents",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=reason or _limit_reason(effective_id, "agents", limit),
        )


async def assert_can_create_document(
    db: aiosqlite.Connection, workspace: dict
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    used = await count_documents(db, workspace["id"])
    allowed, reason = check_limit_for_plan(effective_id, "documents", used)
    if not allowed:
        limit = get_limits_for_plan(effective_id)["documents"]
        raise limit_error(
            resource="documents",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=reason or _limit_reason(effective_id, "documents", limit),
        )


async def assert_can_create_website_source(
    db: aiosqlite.Connection, workspace: dict
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    used = await count_website_sources(db, workspace["id"])
    allowed, reason = check_limit_for_plan(
        effective_id, "website_sources", used
    )
    if not allowed:
        limit = get_limits_for_plan(effective_id)["website_sources"]
        raise limit_error(
            resource="website_sources",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=reason
            or _limit_reason(effective_id, "website sources", limit),
        )


async def assert_can_index_page(
    db: aiosqlite.Connection,
    workspace_id: str,
    *,
    replacing: bool = False,
) -> None:
    """Gate a new/changed website page against the workspace page allowance."""
    if replacing:
        return
    workspace = await get_workspace(db, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    plan, _, effective_id = await resolve_plan(db, workspace)
    used = await pages_indexed_used(db, workspace_id)
    allowed, reason = check_limit_for_plan(
        effective_id, "pages_indexed", used
    )
    if not allowed:
        limit = get_limits_for_plan(effective_id)["pages_indexed"]
        raise limit_error(
            resource="pages_indexed",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=reason
            or _limit_reason(effective_id, "indexed pages", limit),
        )


async def assert_can_create_api_key(
    db: aiosqlite.Connection, workspace: dict
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    limits = get_limits_for_plan(effective_id)
    limit = limits["api_keys"]
    used = await count_api_keys(db, workspace["id"])
    allowed, reason = check_limit_for_plan(effective_id, "api_keys", used)
    if not allowed:
        message = (
            "Developer API access is not available on the Free plan. "
            "Upgrade to Standard or Pro."
            if limit == 0
            else reason
            or "Your plan's API-key allowance is full. Upgrade for more keys."
        )
        raise limit_error(
            resource="api_keys",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=message,
        )


async def assert_can_create_embed_token(
    db: aiosqlite.Connection, workspace: dict, agent_id: str
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    used = await count_embed_tokens(db, agent_id)
    allowed, reason = check_limit_for_plan(
        effective_id, "embed_tokens", used
    )
    if not allowed:
        limit = get_limits_for_plan(effective_id)["embed_tokens"]
        raise limit_error(
            resource="embed_tokens",
            plan=plan,
            plan_id=effective_id,
            used=used,
            limit=limit or 0,
            message=reason
            or _limit_reason(effective_id, "embed tokens per agent", limit),
        )


# ── Website refresh policy ──────────────────────────────────────────────────


async def allowed_refresh_policy_for_workspace(
    db: aiosqlite.Connection, workspace_id: str
) -> str:
    workspace = await get_workspace(db, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    _, _, effective_id = await resolve_plan(db, workspace)
    return str(get_limits_for_plan(effective_id)["website_refresh"])


async def assert_refresh_policy_allowed(
    db: aiosqlite.Connection, workspace: dict, requested: str
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    allowed = str(get_limits_for_plan(effective_id)["website_refresh"])
    if refresh_policy_rank(requested) > refresh_policy_rank(allowed):
        raise limit_error(
            resource="website_refresh",
            plan=plan,
            plan_id=effective_id,
            used=requested,
            limit=allowed,
            message=(
                f"Your {effective_id} plan supports {allowed} website refresh. "
                "Upgrade to Standard or Pro to unlock more frequent refreshes."
            ),
        )


# ── Other legacy gates ──────────────────────────────────────────────────────


async def assert_can_use_response(
    db: aiosqlite.Connection, workspace: dict
) -> tuple[int, str]:
    """Deprecated response-cap gate retained for compatibility.

    The new contract meters chat messages in `usage_monthly`; AI responses are
    still recorded for analytics but are not capped by this function.
    """
    _, end = period_bounds()
    return await responses_used(db, workspace["id"]), end


async def assert_storage_available(
    db: aiosqlite.Connection,
    workspace: dict,
    incoming_bytes: int,
    *,
    exclude_doc_id: Optional[str] = None,
) -> None:
    plan, _, _ = await resolve_plan(db, workspace)
    used = await storage_used_bytes(db, workspace["id"], exclude_doc_id)
    if incoming_bytes < 0:
        incoming_bytes = 0
    if used + incoming_bytes > plan.storage_bytes:
        raise limit_error(
            resource="storage",
            plan=plan,
            used=used,
            limit=plan.storage_bytes,
            message=(
                f"This upload would take you over your "
                f"{format_bytes(plan.storage_bytes)} knowledge-base allowance "
                f"({format_bytes(used)} used). Delete a document or upgrade to "
                "free up space."
            ),
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )


async def assert_can_import_social_media(
    db: aiosqlite.Connection, workspace: dict, agent_id: str
) -> tuple[int, int]:
    """Raise 402 when an agent's legacy social-media source allowance is full."""
    plan, _, _ = await resolve_plan(db, workspace)
    used = await social_media_sources_used(db, agent_id)
    if used >= plan.max_social_media_sources:
        raise limit_error(
            resource="social_media_sources",
            plan=plan,
            used=used,
            limit=plan.max_social_media_sources,
            code="plan_limit_reached",
            message=(
                f"This agent has reached its {plan.name} plan limit of "
                f"{plan.max_social_media_sources} social media sources. "
                "Remove an imported link or upgrade to add another."
            ),
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )
    return used, plan.max_social_media_sources


async def require_developer_api(
    db: aiosqlite.Connection, workspace: dict
) -> None:
    plan, _, effective_id = await resolve_plan(db, workspace)
    if not plan.features.get("developer_api"):
        raise limit_error(
            resource="developer_api",
            plan=plan,
            plan_id=effective_id,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message=(
                "Developer API access is included in Standard and Pro. "
                "Upgrade to create API keys and call your agents from your "
                "own backend."
            ),
        )


async def record_ai_response(db: aiosqlite.Connection, workspace_id: str) -> None:
    """Append one metered AI response for the current UTC month."""
    await db.execute(
        """INSERT INTO usage_events
           (id, workspace_id, kind, quantity, created_at)
           VALUES (?, ?, 'ai_response', 1, ?)""",
        (str(uuid.uuid4()), workspace_id, _utc_now().isoformat()),
    )
    await db.commit()


# ── Chat quota ──────────────────────────────────────────────────────────────


async def check_chat_limit(
    db: aiosqlite.Connection,
    user_id: str,
    user: Optional[dict],
    *,
    plan_id: Optional[str] = None,
) -> int:
    """
    Check and increment the account's monthly chat counter.

    Raises 429 when the effective plan's allowance is exhausted. The counter is
    incremented before the LLM call, matching the product's "chat messages"
    contract (attempts count, not only successful answers).
    """
    limits = (
        get_limits_for_plan(plan_id)
        if plan_id
        else get_limits_for_plan(resolve_effective_plan(user))
    )
    max_messages = limits["chat_messages"]
    month = _utc_now().strftime("%Y-%m")
    used = await chat_messages_used(db, user_id, month)
    if max_messages is not None and used >= int(max_messages):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "chat_messages_limit_reached",
                "resource": "chat_messages",
                "message": (
                    f"You have used all {max_messages} chat messages for this "
                    "month. Upgrade to Standard or Pro for more."
                ),
                "plan": plan_id or resolve_effective_plan(user),
                "used": used,
                "limit": max_messages,
                "upgrade_required": True,
                "payments_configured": False,
            },
        )
    await db.execute(
        """INSERT INTO usage_monthly (id, user_id, month, chat_messages)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(user_id, month)
           DO UPDATE SET chat_messages = usage_monthly.chat_messages + 1""",
        (str(uuid.uuid4()), user_id, month),
    )
    await db.commit()
    return used + 1


async def assert_can_chat(
    db: aiosqlite.Connection, workspace: dict
) -> int:
    """Resolve the workspace owner and enforce the account chat allowance."""
    _, owner, effective_id = await resolve_plan(db, workspace)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace owner not found"
        )
    return await check_chat_limit(
        db, owner["id"], owner, plan_id=effective_id
    )


# ── Summary (billing API) ───────────────────────────────────────────────────


def _percent(used: int, limit: int | None) -> float:
    if limit is None or limit <= 0:
        return 0.0
    return round(min(100.0, (used / limit) * 100.0), 1)


def _counter(used: int, limit: int | None) -> dict[str, Any]:
    return {
        "used": used,
        "limit": limit,
        "percent": _percent(used, limit),
        "unlimited": limit is None,
    }


async def billing_summary(db: aiosqlite.Connection, workspace: dict) -> dict:
    plan, owner, effective_id = await resolve_plan(db, workspace)
    start, end = period_bounds()
    agents_used = await count_agents(db, workspace["id"])
    documents_used = await count_documents(db, workspace["id"])
    pages_used = await pages_indexed_used(db, workspace["id"])
    websites_used = await count_website_sources(db, workspace["id"])
    api_keys_used = await count_api_keys(db, workspace["id"])
    embed_tokens_used = await count_embed_tokens_for_workspace(
        db, workspace["id"]
    )
    storage = await storage_used_bytes(db, workspace["id"])
    chat_used = (
        await chat_messages_used(db, owner["id"]) if owner is not None else 0
    )
    limits = get_limits_for_plan(effective_id)
    # Embed tokens are limited per agent, so the workspace meter shows the
    # combined allowance for the agents that currently exist (or one slot
    # before the first agent is created).
    embed_limit = limits["embed_tokens"]
    embed_capacity = (
        None if embed_limit is None else int(embed_limit) * max(agents_used, 1)
    )
    trial = get_trial_status(owner) if owner else {
        "is_trial": False,
        "trial_ends_at": None,
        "days_remaining": None,
        "effective_plan": effective_id,
        "base_plan": "free",
    }

    return {
        "workspace_id": workspace["id"],
        "plan": plan.as_dict(),
        "plans": [candidate.as_dict() for candidate in plan_list()],
        "is_trial": trial["is_trial"],
        "base_plan": trial["base_plan"],
        "effective_plan": effective_id,
        "trial_ends_at": trial["trial_ends_at"],
        "days_remaining": trial["days_remaining"],
        "usage": {
            "agents": _counter(agents_used, limits["agents"]),
            "documents": _counter(documents_used, limits["documents"]),
            "pages_indexed": _counter(pages_used, limits["pages_indexed"]),
            "website_sources": _counter(
                websites_used, limits["website_sources"]
            ),
            "api_keys": _counter(api_keys_used, limits["api_keys"]),
            "embed_tokens": _counter(embed_tokens_used, embed_capacity),
            "chat_messages": {
                **_counter(chat_used, limits["chat_messages"]),
                "period_start": start,
                "period_end": end,
                "resets_at": end,
            },
            "storage": {
                "used_bytes": storage,
                "limit_bytes": plan.storage_bytes,
                "percent": _percent(storage, plan.storage_bytes),
            },
            "members": {
                "used": 1,  # the owner; invites are not implemented yet
                "limit": plan.max_members,
                "percent": _percent(1, plan.max_members),
                "unlimited": False,
                "enforced": False,
            },
        },
        "period": {"start": start, "end": end, "resets_at": end},
        "plan_started_at": workspace.get("plan_started_at"),
        "payments_configured": False,
        "upgrade_available": False,
        "launch_note": (
            "Every new account includes a 21-day Pro trial. After the trial, "
            "the account moves to Free automatically. Paid plans are shown for "
            "transparency and will become available once payments go live."
        ),
    }


# ── Operator tooling ────────────────────────────────────────────────────────


async def set_workspace_plan(
    db: aiosqlite.Connection, workspace_id: str, plan_id: str
) -> dict:
    """Change a workspace's plan. Intended for operators/tests only.

    There is deliberately no self-service upgrade endpoint: without a payment
    provider, letting the public API set `pro` would give the product away.
    """
    normalized = (plan_id or "").strip().lower()
    if normalized not in PLAN_CATALOG:
        raise ValueError(
            f"Unknown plan '{plan_id}'. Choose one of: {', '.join(PLAN_CATALOG)}"
        )
    now = _utc_now().isoformat()
    await db.execute(
        "UPDATE workspaces SET plan = ?, plan_started_at = ? WHERE id = ?",
        (normalized, now, workspace_id),
    )
    await db.commit()
    workspace = await get_workspace(db, workspace_id)
    if workspace is None:
        raise ValueError(f"Workspace '{workspace_id}' not found")
    log.info(
        "Workspace plan changed", workspace_id=workspace_id, plan=normalized
    )
    return workspace
