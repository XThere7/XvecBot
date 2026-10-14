"""
api/developer.py (Phase 6 — BotBase developer platform).

Public REST API for third-party developers (mobile apps, WhatsApp/Telegram
bots, CRMs). Auth is a long-lived X-API-Key (SHA-256 verified, never stored
plaintext) — NOT the dashboard JWT.

Security model per request: key → workspace → owner; the agent must live in
the key's workspace AND (when restricted) in allowed_agents AND be active.
Every failure mode returns a stable JSON {"error": ...} shape — never a
stack trace.
"""
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.logging import get_logger
from ..services import agent_chat_service, api_key_service

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Developer API"])

MAX_MESSAGE_LENGTH = 4000

# ── Per-key rate limiter ──────────────────────────────────────────────────────
# Same in-process fixed-window approach as public.py's per-token limiter.
# Keyed by key_hash (never the raw key) so compromise of a memory dump still
# reveals nothing usable. The Phase 4 global middleware only covers /auth and
# /public — developer traffic needs its own gate.
DEV_RATE_LIMIT_MAX = 60
DEV_RATE_LIMIT_WINDOW = 60.0

_dev_rate_limit: dict[str, list[float]] = defaultdict(list)


def _check_dev_rate_limit(key_hash: str) -> int:
    """
    Allow DEV_RATE_LIMIT_MAX requests per window per key.
    Returns 0 when allowed, else the Retry-After seconds on 429.
    """
    import hashlib

    bucket = hashlib.sha256(key_hash.encode("utf-8")).hexdigest()
    now = time.monotonic()
    cutoff = now - DEV_RATE_LIMIT_WINDOW
    _dev_rate_limit[bucket] = [t for t in _dev_rate_limit[bucket] if t > cutoff]
    if len(_dev_rate_limit[bucket]) >= DEV_RATE_LIMIT_MAX:
        return int(DEV_RATE_LIMIT_WINDOW - (now - _dev_rate_limit[bucket][0])) + 1
    _dev_rate_limit[bucket].append(now)
    return 0


def _dev_error(status_code: int, error: str, **extra) -> JSONResponse:
    """
    Developer error contract: flat {"error": ...} body (NOT FastAPI's nested
    {"detail": ...} shape — HTTPException would wrap it). Never includes
    tracebacks or internal details.
    """
    return JSONResponse(
        status_code=status_code, content={"error": error, **extra}
    )


async def _require_dev_key(
    x_api_key: Optional[str], db
) -> dict | JSONResponse:
    """Verify the X-API-Key header → key record, else a 401 response."""
    record = await api_key_service.verify_api_key(db, x_api_key or "")
    if record is None:
        return _dev_error(401, "Invalid or revoked API key.")
    return record


class DevChatRequest(BaseModel):
    # No length validators here on purpose: empty/oversize messages must
    # surface as the spec's 400 {"error": ...}, not FastAPI's 422 shape.
    agent_id: str = Field(..., min_length=1)
    message: str = ""
    conversation_id: Optional[str] = None
    stream: bool = False  # reserved: streaming is a future transport


@router.get("/health", summary="Developer API health (no auth)")
async def dev_health():
    """Liveness probe for integrators — no key required."""
    return {
        "status": "ok",
        "version": "1.0",
        "docs": "https://docs.botbase.tz/api",
    }


@router.get("/agents", summary="List agents this key may call")
async def dev_list_agents(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Only agents in the key's workspace, honouring allowed_agents."""
    async with get_db() as db:
        record = await _require_dev_key(x_api_key, db)
        if isinstance(record, JSONResponse):
            return record
        async with db.execute(
            "SELECT * FROM agents WHERE workspace_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC",
            (record["workspace_id"],),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    allowed = record["allowed_agents"]
    if allowed is not None:
        allowed_set = set(allowed)
        rows = [r for r in rows if r["id"] in allowed_set]
    return {
        "agents": [
            {
                "agent_id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "language": r["language"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ],
        "workspace_id": record["workspace_id"],
    }


@router.post("/chat", summary="Chat with an agent via API key")
async def dev_chat(
    payload: DevChatRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Core developer contract: agent_id + message → answer + citations.
    conversation_id threads multi-turn memory (bound to the agent, 404 on
    foreign ids — same rule as the dashboard chat).
    """
    message = (payload.message or "").strip()
    if not message:
        return _dev_error(400, "message is required and must not be empty.")
    if len(message) > MAX_MESSAGE_LENGTH:
        return _dev_error(400, "message exceeds 4000 character limit.")
    if payload.stream:
        return _dev_error(
            400, "streaming is not supported yet — call with stream=false."
        )

    async with get_db() as db:
        record = await _require_dev_key(x_api_key, db)
        if isinstance(record, JSONResponse):
            return record

        retry_after = _check_dev_rate_limit(record["id"])
        if retry_after:
            return _dev_error(
                429,
                "Rate limit exceeded.",
                retry_after_seconds=retry_after,
            )

        # 1. Agent must exist and be active.
        async with db.execute(
            "SELECT * FROM agents WHERE id = ?", (payload.agent_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or not row["is_active"]:
            return _dev_error(404, "Agent not found or is not active.")
        agent = dict(row)

        # 2. Hard workspace scoping: the agent must live in the key's workspace.
        if agent["workspace_id"] != record["workspace_id"]:
            return _dev_error(
                403,
                f"Agent {payload.agent_id} does not belong to this API key's workspace.",
            )

        # 3. Optional per-agent restriction on the key itself.
        if record["allowed_agents"] is not None and payload.agent_id not in set(
            record["allowed_agents"]
        ):
            return _dev_error(
                403,
                f"This API key is not authorised to access agent {payload.agent_id}.",
            )

        try:
            result = await agent_chat_service.chat_with_agent(
                agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                message=message,
                db=db,
            )
        except Exception as exc:
            # Foreign conversation_id surfaces from chat_with_agent — map to
            # the developer contract without leaking internals.
            from fastapi import HTTPException as _HTTPException

            if isinstance(exc, _HTTPException) and exc.status_code == 404:
                return _dev_error(404, "Conversation not found.")
            log.error("Developer chat failed", error=str(exc))
            return _dev_error(
                500, "An internal error occurred. Please try again."
            )

    return {
        "answer": result["answer"],
        "citations": [
            {"source": s.get("filename", "unknown"), "chunk_index": s.get("chunk_index", 0)}
            for s in (result.get("sources") or [])
        ],
        "conversation_id": result["conversation_id"],
        "agent_id": payload.agent_id,
        "model_used": result.get("model_used", ""),
    }
