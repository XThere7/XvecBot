"""
api/admin/admins.py
Admin management — superadmin only. Creates or promotes admin accounts,
sends a set-password invite by email (or returns a one-time setup link when
mail is not configured), edits permissions via presets or an explicit list,
suspends, deletes, forces sign-out, and shows each admin's activity.

The superadmin role can never be assigned here — only via the bootstrap CLI.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .deps import ALL_PERMISSIONS, PERMISSION_PRESETS, require_superadmin, verify_reauth
from ...core.auth import hash_password
from ...core.config import settings
from ...core.database import get_db
from ...emails import deliver_admin_invite_email
from ...services import admin_service, password_reset_service

router = APIRouter()


class CreateAdminBody(BaseModel):
    email: str = Field(..., max_length=255)
    permissions: list[str] = Field(default_factory=list)
    preset: str | None = None
    reason: str = Field(default="", max_length=500)
    reauth_password: str = Field(..., min_length=1, max_length=255)
    reauth_code: str = Field(default="", max_length=32)


class PermissionsBody(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    preset: str | None = None
    reason: str = Field(default="", max_length=500)


class SuspendBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class ReactivateBody(BaseModel):
    reason: str = Field(default="", max_length=500)


def _resolve_permissions(permissions: list[str], preset: str | None) -> list[str]:
    if preset and preset in PERMISSION_PRESETS:
        chosen = list(PERMISSION_PRESETS[preset])
    else:
        chosen = [str(item) for item in (permissions or [])]
    # Only ever allow keys from the grantable list.
    return [item for item in chosen if item in ALL_PERMISSIONS]


def _admin_row(row) -> dict:
    item = dict(row)
    try:
        item["permissions"] = json.loads(item.get("permissions") or "[]")
    except ValueError:
        item["permissions"] = []
    return item


@router.get("/admins", summary="List admins")
async def list_admins(user: dict = Depends(require_superadmin)):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, email, role, permissions, created_at, last_login_at, "
            "suspended_at, totp_enabled FROM users "
            "WHERE role IN ('admin', 'superadmin') ORDER BY created_at ASC"
        )
        rows = await cur.fetchall()
    return {"items": [_admin_row(dict(r)) for r in rows]}


@router.post("/admins", summary="Create or promote an admin")
async def create_admin(
    body: CreateAdminBody,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
        raise HTTPException(status_code=403, detail="Re-authentication failed.")

    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    permissions = _resolve_permissions(body.permissions, body.preset)
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE email = ?", (email,)
        )
        existing = await cur.fetchone()
        if existing and existing["role"] == "superadmin":
            raise HTTPException(
                status_code=403,
                detail="Cannot change the superadmin account.",
            )
        if existing and existing["role"] == "admin":
            raise HTTPException(
                status_code=409, detail="This address is already an admin."
            )

        if existing:
            admin_id = existing["id"]
            await db.execute(
                "UPDATE users SET role = 'admin', permissions = ? WHERE id = ?",
                (json.dumps(permissions), admin_id),
            )
        else:
            admin_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO users (id, email, hashed_password, is_active, "
                "created_at, plan, trial_ends_at, role, permissions) "
                "VALUES (?, ?, ?, 1, ?, 'free', NULL, 'admin', ?)",
                (
                    admin_id,
                    email,
                    hash_password(secrets.token_hex(16)),  # unusable until invite
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(permissions),
                ),
            )

        # Set-password link reuses the reset-token mechanism with its own,
        # longer (still short) expiry.
        raw_token = await password_reset_service.create_reset_token(
            db, admin_id, request.client.host if request.client else "admin",
            ttl_minutes=settings.admin_invite_ttl_minutes,
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.create", target_type="admin",
            target_id=admin_id,
            summary=f"admin created/promoted with {len(permissions)} permissions",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()

    setup_url = (
        f"{settings.resolved_frontend_url}/reset-password?token={raw_token}"
    )
    # With a real mail backend the invite goes by email; otherwise the URL is
    # returned exactly once in this response.
    if settings.email_backend in ("file", "memory"):
        background_tasks.add_task(deliver_admin_invite_email, email, raw_token)
        invite_url = setup_url
    else:
        background_tasks.add_task(deliver_admin_invite_email, email, raw_token)
        invite_url = None

    return {
        "admin_id": admin_id,
        "email": email,
        "permissions": permissions,
        "invite_sent_by_email": invite_url is None,
        **({"setup_url": invite_url, "setup_url_note":
            "Mail is not configured; show this one-time link to the new admin."}
           if invite_url else {}),
    }


@router.patch("/admins/{admin_id}/permissions", summary="Edit an admin's permissions")
async def edit_permissions(
    admin_id: str,
    body: PermissionsBody,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    permissions = _resolve_permissions(body.permissions, body.preset)
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Admin not found.")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot edit the superadmin.")
        await db.execute(
            "UPDATE users SET permissions = ? WHERE id = ?",
            (json.dumps(permissions), admin_id),
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.permissions", target_type="admin",
            target_id=admin_id,
            summary=f"permissions set to {permissions}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"permissions": permissions}


@router.post("/admins/{admin_id}/suspend", summary="Suspend an admin")
async def suspend_admin(
    admin_id: str,
    body: SuspendBody,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Admin not found.")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot suspend the superadmin.")
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE users SET suspended_at = ?, suspended_reason = ? WHERE id = ?",
            (now, body.reason, admin_id),
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.suspend", target_type="admin",
            target_id=admin_id, summary=f"suspended: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"suspended_at": now}


@router.post("/admins/{admin_id}/reactivate", summary="Reactivate an admin")
async def reactivate_admin(
    admin_id: str,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Admin not found.")
        await db.execute(
            "UPDATE users SET suspended_at = NULL, suspended_reason = NULL "
            "WHERE id = ?",
            (admin_id,),
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.reactivate", target_type="admin",
            target_id=admin_id, summary="reactivated",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"suspended_at": None}


@router.post("/admins/{admin_id}/force-signout", summary="Force an admin's sign-out")
async def force_signout(
    admin_id: str,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Admin not found.")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot sign out the superadmin.")
        await db.execute(
            "UPDATE users SET password_changed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), admin_id),
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.force_signout", target_type="admin",
            target_id=admin_id, summary="sessions invalidated",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"signed_out": True}


@router.delete("/admins/{admin_id}", summary="Delete an admin account")
async def delete_admin(
    admin_id: str,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Admin not found.")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot delete the superadmin.")
        await db.execute(
            "UPDATE users SET role = 'user', permissions = NULL, "
            "suspended_at = NULL WHERE id = ?",
            (admin_id,),
        )
        await admin_service.write_audit(
            db, actor=user, action="admin.delete", target_type="admin",
            target_id=admin_id, summary="demoted to user",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"deleted": True}


@router.get("/admins/{admin_id}/activity", summary="An admin's activity")
async def admin_activity(
    admin_id: str,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE actor_id = ?", (admin_id,)
        )
        total = int((await cur.fetchone())["n"])
        cur = await db.execute(
            "SELECT ts, action, target_type, target_id, summary, ip "
            "FROM audit_log WHERE actor_id = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (admin_id, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }
