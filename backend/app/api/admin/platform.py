"""
api/admin/platform.py
Platform controls — superadmin only, re-authenticated, every change audited.

Keys in platform_settings:
  signups_open        "true" | "false" (registration gate)
  maintenance_message "" | banner text
  emergency_off       "true" | "false" (widget + hosted + developer API stop)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_superadmin, verify_reauth
from ...core.database import get_db
from ...services import admin_service

router = APIRouter()

DEFAULTS = {"signups_open": "true", "maintenance_message": "", "emergency_off": "false"}


class PlatformSettingsBody(BaseModel):
    signups_open: bool | None = None
    maintenance_message: str | None = Field(default=None, max_length=500)
    emergency_off: bool | None = None
    reason: str = Field(default="", max_length=500)
    reauth_password: str = Field(..., min_length=1, max_length=255)
    reauth_code: str = Field(default="", max_length=32)


@router.get("/platform/settings", summary="Read platform controls")
async def read_settings(user: dict = Depends(require_superadmin)):
    async with get_db() as db:
        values = await admin_service.get_platform_settings(db)
    merged = dict(DEFAULTS)
    merged.update(values)
    return {
        "signups_open": merged["signups_open"] != "false",
        "maintenance_message": merged["maintenance_message"],
        "emergency_off": merged["emergency_off"] == "true",
    }


@router.put("/platform/settings", summary="Change platform controls (audited)")
async def update_settings(
    body: PlatformSettingsBody,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
        async with get_db() as db:
            await admin_service.write_audit(
                db, actor=user, action="platform.settings_denied", target_type=None,
                target_id=None, summary="re-authentication failed",
                ip=request.client.host if request.client else None,
            )
            await db.commit()
        raise HTTPException(status_code=403, detail="Re-authentication failed.")

    changed: list[str] = []
    async with get_db() as db:
        if body.signups_open is not None:
            await admin_service.set_platform_setting(
                db, "signups_open", "true" if body.signups_open else "false",
                user.get("email") or user["id"],
            )
            changed.append(f"signups_open={body.signups_open}")
        if body.maintenance_message is not None:
            await admin_service.set_platform_setting(
                db, "maintenance_message", body.maintenance_message,
                user.get("email") or user["id"],
            )
            changed.append("maintenance_message")
        if body.emergency_off is not None:
            await admin_service.set_platform_setting(
                db, "emergency_off", "true" if body.emergency_off else "false",
                user.get("email") or user["id"],
            )
            changed.append(f"emergency_off={body.emergency_off}")
        await admin_service.write_audit(
            db, actor=user, action="platform.settings", target_type="platform",
            target_id=None,
            summary=f"{', '.join(changed)}: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return {"changed": changed}
