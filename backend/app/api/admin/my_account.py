"""
api/admin/my_account.py
Every admin's own account surface: profile, password change, TOTP setup /
verification / disable, recovery-code regeneration, and recent activity.

TOTP is mandatory for the superadmin: the disable endpoint refuses it.
"""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_admin_role, verify_reauth
from ...core.auth import hash_password
from ...core.config import settings
from ...core.database import get_db
from ...core import totp
from ...services import admin_service

router = APIRouter()


class PasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=255)
    confirm_password: str | None = None
    reauth_code: str = Field(default="", max_length=32)


class TotpVerifyBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=32)


class ReauthBody(BaseModel):
    reauth_password: str = Field(..., min_length=1, max_length=255)
    reauth_code: str = Field(default="", max_length=32)


def _qr_data_uri(uri: str) -> str:
    import qrcode

    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@router.get("/my-account", summary="My admin profile")
async def my_account(user: dict = Depends(require_admin_role)):
    from .deps import parsed_permissions

    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "permissions": parsed_permissions(user),
        "totp_enabled": bool(user.get("totp_enabled")),
        "last_login_at": user.get("last_login_at"),
        "created_at": user.get("created_at"),
    }


@router.post("/my-account/password", summary="Change my password")
async def change_password(
    body: PasswordBody,
    request: Request,
    user: dict = Depends(require_admin_role),
):
    if (
        body.confirm_password is not None
        and body.confirm_password != body.new_password
    ):
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    if not verify_reauth(
        user, body.current_password, body.reauth_code or None
    ):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET hashed_password = ?, password_changed_at = ? "
            "WHERE id = ?",
            (hash_password(body.new_password), now, user["id"]),
        )
        await admin_service.write_audit(
            db, actor=user, action="account.password_change", target_type="admin",
            target_id=user["id"], summary="password changed",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"message": "Password changed. Other sessions have been signed out."}


@router.post("/my-account/totp/setup", summary="Start TOTP enrolment")
async def totp_setup(
    body: ReauthBody,
    user: dict = Depends(require_admin_role),
):
    if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
        raise HTTPException(status_code=403, detail="Re-authentication failed.")
    if user.get("totp_enabled"):
        raise HTTPException(status_code=409, detail="Two-factor is already enabled.")

    secret = totp.generate_secret()
    encrypted = totp.encrypt_secret(secret)
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET totp_secret = ? WHERE id = ?", (encrypted, user["id"])
        )
        await db.commit()

    uri = totp.provisioning_uri(secret, user["email"])
    return {
        "secret": secret,  # shown once during setup
        "otpauth_uri": uri,
        "qr_data_uri": _qr_data_uri(uri),
        "note": "Scan the QR or enter the secret in your authenticator, then "
                "confirm with a code.",
    }


@router.post("/my-account/totp/verify", summary="Verify TOTP and enable 2FA")
async def totp_verify(
    body: TotpVerifyBody,
    user: dict = Depends(require_admin_role),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT totp_secret, totp_enabled FROM users WHERE id = ?", (user["id"],)
        )
        row = await cur.fetchone()
    secret = totp.decrypt_secret(row["totp_secret"]) if row and row["totp_secret"] else None
    if not secret or not totp.verify_code(secret, body.code):
        raise HTTPException(status_code=401, detail="Invalid verification code.")

    plain_codes, hashed_codes = totp.generate_recovery_codes()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET totp_enabled = 1, recovery_codes = ? WHERE id = ?",
            (json.dumps(hashed_codes), user["id"]),
        )
        await admin_service.write_audit(
            db, actor=user, action="account.totp_enabled", target_type="admin",
            target_id=user["id"], summary="two-factor enabled",
        )
        await db.commit()
    return {
        "enabled": True,
        "recovery_codes": plain_codes,  # shown exactly once
        "note": "Store these single-use recovery codes somewhere safe.",
    }


@router.post("/my-account/totp/disable", summary="Disable 2FA (not for superadmin)")
async def totp_disable(
    body: ReauthBody,
    user: dict = Depends(require_admin_role),
):
    if user.get("role") == "superadmin":
        raise HTTPException(
            status_code=403, detail="The master admin must keep two-factor enabled."
        )
    if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
        raise HTTPException(status_code=403, detail="Re-authentication failed.")
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET totp_enabled = 0, totp_secret = NULL, "
            "recovery_codes = NULL WHERE id = ?",
            (user["id"],),
        )
        await admin_service.write_audit(
            db, actor=user, action="account.totp_disabled", target_type="admin",
            target_id=user["id"], summary="two-factor disabled",
        )
        await db.commit()
    return {"enabled": False}


@router.post("/my-account/recovery-codes", summary="Regenerate recovery codes")
async def regenerate_codes(
    body: ReauthBody,
    user: dict = Depends(require_admin_role),
):
    if not user.get("totp_enabled"):
        raise HTTPException(status_code=409, detail="Enable two-factor first.")
    if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
        raise HTTPException(status_code=403, detail="Re-authentication failed.")
    plain_codes, hashed_codes = totp.generate_recovery_codes()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET recovery_codes = ? WHERE id = ?",
            (json.dumps(hashed_codes), user["id"]),
        )
        await admin_service.write_audit(
            db, actor=user, action="account.recovery_codes", target_type="admin",
            target_id=user["id"], summary="recovery codes regenerated",
        )
        await db.commit()
    return {"recovery_codes": plain_codes}


@router.get("/my-account/activity", summary="My recent admin activity")
async def my_activity(
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_admin_role),
):
    async with get_db() as db:
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE actor_id = ?", (user["id"],)
        )
        total = int((await cur.fetchone())["n"])
        cur = await db.execute(
            "SELECT ts, action, target_type, target_id, summary, ip "
            "FROM audit_log WHERE actor_id = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (user["id"], size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }
