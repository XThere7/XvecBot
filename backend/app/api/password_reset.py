"""
api/password_reset.py
Self-service password recovery — request, validate and reset.

Anti-enumeration contract
-------------------------
``POST /auth/forgot-password`` always returns the same neutral body for
registered, unknown, inactive and malformed addresses. All real work (user
lookup, token creation, mail) happens in a background task, so response time
does not reveal whether an account exists. Rate limiting raises a dedicated
exception that is mapped to 429 with the *same* neutral body.

Token handling
--------------
Raw tokens are never logged, never stored (only their SHA-256), and never
touched by any middleware that records request data. Consumption is a single
conditional UPDATE ... RETURNING so a token can only ever be used once, even
under concurrent requests.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core.auth import hash_password
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.rate_limit import _client_ip
from ..emails import deliver_password_changed_notice, deliver_password_reset_email
from ..services import password_reset_service as service
from ..services.password_reset_service import FORGOT_RESPONSE, PasswordResetRateLimited

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

GENERIC_INVALID = "This reset link is invalid or has expired."


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=service.MIN_PASSWORD_LENGTH)
    confirm_password: str | None = None


async def process_forgot_request(email: str, ip: str) -> None:
    """Background task: lookup + token + mail. Never raises into the request."""
    try:
        async with get_db() as db:
            cur = await db.execute(
                "SELECT id, is_active FROM users WHERE email = ?", (email,)
            )
            row = await cur.fetchone()
            if row is None or not row["is_active"]:
                return
            raw_token = await service.create_reset_token(db, row["id"], ip)
            await db.commit()
        await deliver_password_reset_email(email, raw_token)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Password reset request processing failed", outcome=type(exc).__name__)


@router.post(
    "/forgot-password",
    summary="Request a password reset link (no account enumeration)",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Always answers with the same 200 body. A 429 uses the same body so the
    limiter confirms nothing either.
    """
    email = payload.email.strip().lower()
    plausible = service.looks_like_email(email)
    try:
        if plausible:
            service.check_email_rate_limit(email)
        service.check_ip_rate_limit(_client_ip(request))
    except PasswordResetRateLimited:
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=FORGOT_RESPONSE)

    if plausible:
        background_tasks.add_task(process_forgot_request, email, _client_ip(request))

    return JSONResponse(status_code=status.HTTP_200_OK, content=FORGOT_RESPONSE)


@router.get(
    "/reset-password/validate",
    summary="Check whether a reset token is still usable (no enumeration surface)",
)
async def validate_reset_token(token: str = ""):
    """Reveals nothing beyond valid / invalid for the presented token."""
    if not token:
        return {"valid": False}
    async with get_db() as db:
        valid = await service.is_token_valid(db, token)
    return {"valid": valid}


@router.post(
    "/reset-password",
    summary="Consume a reset token and set a new password",
)
async def reset_password(payload: ResetPasswordRequest, background_tasks: BackgroundTasks):
    """One-time, single-use token; existing sessions are invalidated."""
    if (
        payload.confirm_password is not None
        and payload.confirm_password != payload.new_password
    ):
        # Token deliberately untouched on this path.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    async with get_db() as db:
        user_id = await service.consume_token(db, payload.token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=GENERIC_INVALID,
            )

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE users SET hashed_password = ?, password_changed_at = ? WHERE id = ?",
            (hash_password(payload.new_password), now, user_id),
        )
        # Any other outstanding links for this user die with this one.
        await db.execute(
            "UPDATE password_reset_tokens SET used_at = ? "
            "WHERE user_id = ? AND used_at IS NULL",
            (now, user_id),
        )
        cur = await db.execute("SELECT email FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        email = row["email"] if row else None
        await db.commit()

    if email:
        # Best-effort hijack visibility notice; failures never affect the reset.
        background_tasks.add_task(deliver_password_changed_notice, email)

    log.info("Password reset completed", user_id=user_id)
    return {"message": "Your password has been reset. You can now sign in with your new password."}
