"""
api/public.py
Public embeddable widget — NO authentication.

Any website can embed an agent using an opaque embed token. This router is
intentionally minimal: one chat endpoint and one agent-info endpoint. It applies
an in-process per-token rate limiter and never exposes internal agent config.
"""
import time
from collections import defaultdict
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..models.embed_token import PublicAgentInfo
from ..services import admin_service, embed_service

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
#   chunk_index (and source_url for crawled website pages). That is a label
#   the merchant chose when uploading, it is
#   required for the widget to render citation links, and it is NOT the stored
#   file_path. Audited: _source_metadata_for_chunks() selects only the
#   filename/url columns, so no server path can reach the public payload.
# ─────────────────────────────────────────────────────────────────────────────


def _channel_for_origin(origin: str | None) -> str:
    """widget vs hosted: the hosted chat page shares the public endpoints but
    sends its own origin."""
    from urllib.parse import urlparse

    if origin:
        host = urlparse(origin).hostname
        hosted_host = urlparse(settings.hosted_base_url).hostname
        if host and hosted_host and host == hosted_host:
            return "hosted"
    return "widget"


@router.post("/chat", summary="Public widget chat (no auth)")
async def public_chat(
    payload: PublicChatRequest,
    request: Request,
):
    origin = request.headers.get("origin")

    async with get_db() as db:
        # Platform controls first: the emergency switch answers every public
        # request with a friendly 503 before token validation reveals anything.
        await admin_service.require_platform_available(db)
        # Validate token, agent state and Origin BEFORE consuming the per-token
        # bucket. Otherwise a blocked origin can deny service to the legitimate
        # customer site. The IP-scoped middleware remains the outer abuse gate.
        embed, agent = await embed_service.validate_public_request(
            db, payload.token, origin
        )
        # Owner suspension stops this assistant with the same friendly 503.
        await admin_service.require_owner_active(db, agent["workspace_id"])
        _check_rate_limit(payload.token)
        await embed_service.record_token_use(db, embed["id"])
        channel = _channel_for_origin(origin)
        result = await embed_service.chat_for_public_agent(
            db=db,
            agent=agent,
            message=payload.message,
            conversation_id=payload.conversation_id,
            channel=channel,
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
        await admin_service.require_platform_available(db)
        await admin_service.require_owner_active(db, agent["workspace_id"])
    # icon_url is stored as a same-server path (/static/icons/…); the widget
    # runs on another origin, so hand it an absolute URL. Never expose a
    # filesystem path — stored values are validated to the /static/icons/
    # prefix at upload time, anything else is treated as absent.
    stored_icon = agent.get("icon_url") or ""
    icon_url = None
    if stored_icon.startswith("/static/icons/"):
        icon_url = settings.app_public_url.rstrip("/") + stored_icon
    return PublicAgentInfo(
        name=agent["name"],
        description=agent.get("description"),
        language=agent["language"],
        welcome_message=(
            (agent.get("welcome_message") or "").strip() or DEFAULT_WELCOME_MESSAGE
        ),
        icon_url=icon_url,
    )


def _make_qr_png(payload: str) -> bytes:
    """Render a scannable QR PNG for one short URL (print/shop-window grade)."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/qr/{token}", summary="QR code PNG for the hosted chat page (no auth)")
async def public_qr(token: str):
    """
    Method C: downloadable QR that phone cameras resolve straight to the
    hosted chat page. The encoded URL is always the canonical hosted link —
    client-supplied URLs are never encoded (open-redirect/QR-relay abuse).
    Same token validity rules as the agent-info endpoint.
    """
    async with get_db() as db:
        embed, agent = await embed_service.validate_public_request(db, token, None)
        _ = agent  # validity is the check; no agent fields leave this route.
        await admin_service.require_platform_available(db)
        await admin_service.require_owner_active(db, agent["workspace_id"])
        _check_rate_limit(f"qr:{token}")
        await embed_service.record_token_use(db, embed["id"])
    url = f"{settings.hosted_base_url.rstrip('/')}/chat/{token}"

    import asyncio

    png = await asyncio.to_thread(_make_qr_png, url)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f'inline; filename="botbase-chat-qr.png"',
        },
    )
