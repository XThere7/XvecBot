"""
api/public.py
Public embeddable widget — NO authentication.

Any website can embed an agent using an opaque embed token. This router is
intentionally minimal: one chat endpoint and one agent-info endpoint. It applies
an in-process per-token rate limiter and never exposes internal agent config.
"""
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.logging import get_logger
from ..models.embed_token import PublicAgentInfo
from ..services import embed_service

log = get_logger(__name__)
router = APIRouter(prefix="/public", tags=["Public Widget"])

# Used when the agent owner has not configured a welcome_message. The widget
# falls back to the same string if an older API omits the field entirely.
DEFAULT_WELCOME_MESSAGE = "Hi! How can I help you today?"

# ── In-process rate limiter ───────────────────────────────────────────────────
# token -> list of request timestamps (seconds). Max 20 requests / 60 seconds.
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 60.0

_rate_limit: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(token: str) -> None:
    """Allow up to RATE_LIMIT_MAX requests per RATE_LIMIT_WINDOW per token."""
    now = time.time()
    timestamps = _rate_limit[token]

    # Drop entries outside the window.
    cutoff = now - RATE_LIMIT_WINDOW
    _rate_limit[token] = [t for t in timestamps if t > cutoff]

    if len(_rate_limit[token]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )

    _rate_limit[token].append(now)


class PublicChatRequest(BaseModel):
    token: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC SURFACE — WHAT IS DELIBERATELY NEVER EXPOSED
# ─────────────────────────────────────────────────────────────────────────────
# These routes are unauthenticated by design: any website may hold an embed
# token, so everything the browser receives is treated as public. The response
# below is assembled field-by-field from the agent pipeline result rather than
# serialised wholesale, so a new key added to the pipeline cannot leak by
# accident. The following are intentionally excluded:
#
#   workspace_id, owner_id  - identify the merchant; anyone holding the token
#                             already has access, but the ids are not needed
#                             and would aid enumeration.
#   system_prompt           - the merchant's internal instructions. Exposing
#                             them invites prompt-extraction attempts and leaks
#                             business logic.
#   model, model_used       - the merchant's provider/LLM choice and fallback
#                             chain. Exposing it is a commercial secret and
#                             invites model-targeted abuse.
#   temperature, language   - internal agent configuration.
#   file_path               - absolute server paths (documents.file_path).
#                             Reveals the host filesystem layout.
#   document_id, chunk_id,
#   agent_id, message ids   - internal DB primary keys. conversation_id is the
#                             only id returned, because the widget must send it
#                             back to continue the thread; it is an opaque UUID
#                             and grants no other access.
#   request_count, last_used_at, embed token metadata - usage telemetry, the
#                             merchant's side of the contract, not the visitor's.
#
# Deliberately INCLUDED: the generated answer, the citation sources, and
# conversation_id.
#   sources[] carries the *display* filename of the cited document
#   (documents/workspace_documents.filename, e.g. "pricing.pdf") and its
#   chunk_index. That is a label the merchant chose when uploading, it is
#   required for the widget to render citation links, and it is NOT the stored
#   file_path. Audited: _filenames_for_chunks() selects only the filename
#   column, so no server path can reach the public payload.
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/chat", summary="Public widget chat (no auth)")
async def public_chat(
    payload: PublicChatRequest,
    request: Request,
):
    _check_rate_limit(payload.token)

    origin = request.headers.get("origin")

    async with get_db() as db:
        result = await embed_service.public_chat(
            db=db,
            token=payload.token,
            message=payload.message,
            conversation_id=payload.conversation_id,
            origin=origin,
        )

    # Strip internal fields — the public surface exposes only these three.
    # See the audit note above for the full list of what is withheld.
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "conversation_id": result["conversation_id"],
    }


@router.get("/agent/{token}", summary="Public agent info for widget UI (no auth)")
async def public_agent_info(
    token: str,
):
    async with get_db() as db:
        agent = await embed_service.resolve_token(db, token)
    return PublicAgentInfo(
        name=agent["name"],
        description=agent.get("description"),
        language=agent["language"],
        welcome_message=(
            (agent.get("welcome_message") or "").strip() or DEFAULT_WELCOME_MESSAGE
        ),
    )
