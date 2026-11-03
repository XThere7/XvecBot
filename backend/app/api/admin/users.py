"""
api/admin/users.py
User management: list/detail, suspend/reactivate, plan and trial changes,
welcome/reset email resend, and permanent deletion (superadmin, typed
confirmation, re-authentication). Every mutation is audited.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .deps import require_permission, require_superadmin, verify_reauth
from ...core.database import get_db
from ...core.logging import get_logger
from ...core.plan import normalize_plan_id, PLAN_IDS
from ...emails import deliver_password_reset_email, deliver_welcome_email
from ...services import admin_service, password_reset_service
from ...services.password_reset_service import MIN_PASSWORD_LENGTH

log = get_logger(__name__)
router = APIRouter()

USERS_SORTABLE = {
    "created_at", "email", "plan", "trial_ends_at", "last_login_at",
    "suspended_at",
}
USER_FIELDS = (
    "id, email, role, permissions, plan, trial_ends_at, is_active, "
    "created_at, last_login_at, suspended_at, suspended_reason, totp_enabled"
)


def _public_user(row: dict) -> dict:
    user = dict(row)
    try:
        user["permissions"] = json.loads(user.get("permissions") or "[]")
        if not isinstance(user["permissions"], list):
            user["permissions"] = []
    except ValueError:
        user["permissions"] = []
    # Never expose anything sensitive; `id` stays (admin surface).
    return user


class SuspendBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class PlanBody(BaseModel):
    plan: str = Field(..., min_length=1, max_length=20)
    reason: str = Field(default="", max_length=500)


class TrialBody(BaseModel):
    days: int = Field(..., ge=-1, le=365)
    reason: str = Field(default="", max_length=500)


class DeleteBody(BaseModel):
    email_confirmation: str = Field(..., min_length=1, max_length=255)
    reauth_password: str = Field(..., min_length=1, max_length=255)
    reauth_code: str = Field(default="", max_length=32)


async def _fetch_user(db, user_id: str) -> dict | None:
    cur = await db.execute(
        f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None


@router.get("/users", summary="List users (paginated, searchable, filterable)")
async def list_users(
    search: str | None = None,
    plan: str | None = None,
    trial: str | None = None,
    suspended: bool | None = None,
    sort: str | None = None,
    direction: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("users.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("email LIKE ?")
            params.append(like)
        if plan and plan in PLAN_IDS:
            where.append("plan = ?")
            params.append(plan)
        if trial == "active":
            where.append("trial_ends_at > ?")
            params.append(datetime.now(timezone.utc).isoformat())
        elif trial == "expired":
            where.append(
                "trial_ends_at IS NOT NULL AND trial_ends_at <= ?"
            )
            params.append(datetime.now(timezone.utc).isoformat())
        elif trial == "none":
            where.append("trial_ends_at IS NULL")
        if suspended is True:
            where.append("suspended_at IS NOT NULL")
        elif suspended is False:
            where.append("suspended_at IS NULL")

        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur = await db.execute(f"SELECT COUNT(*) AS n FROM users {clause}", tuple(params))
        total = int((await cur.fetchone())["n"])

        order_by = admin_service.validate_sort(sort, USERS_SORTABLE, "created_at")
        direction_sql = admin_service.validate_direction(direction)
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT {USER_FIELDS} FROM users {clause} "
            f"ORDER BY {order_by} {direction_sql} LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()

    return {
        "items": [_public_user(dict(r)) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }


@router.get("/users/{user_id}", summary="User detail")
async def user_detail(
    user_id: str,
    user: dict = Depends(require_permission("users.read")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM workspaces WHERE owner_id = ?", (user_id,)
        )
        target["workspace_count"] = int((await cur.fetchone())["n"])
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM agents a JOIN workspaces w "
            "ON w.id = a.workspace_id WHERE w.owner_id = ?",
            (user_id,),
        )
        target["agent_count"] = int((await cur.fetchone())["n"])
        cur = await db.execute(
            "SELECT id, key_prefix, request_count, last_used_at, is_active, "
            "created_at FROM developer_api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        target["api_keys"] = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute(
            "SELECT id, agent_id, label, request_count, last_used_at, is_active "
            "FROM agent_embed_tokens WHERE agent_id IN "
            "(SELECT a.id FROM agents a JOIN workspaces w ON w.id = a.workspace_id "
            "WHERE w.owner_id = ?) ORDER BY created_at DESC",
            (user_id,),
        )
        target["embed_tokens"] = [dict(r) for r in await cur.fetchall()]
    return target


@router.post("/users/{user_id}/suspend", summary="Suspend a user")
async def suspend_user(
    user_id: str,
    body: SuspendBody,
    request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        if target["role"] == "superadmin" and user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Cannot act on the superadmin.")
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE users SET suspended_at = ?, suspended_reason = ? WHERE id = ?",
            (now, body.reason, user_id),
        )
        await admin_service.write_audit(
            db, actor=user, action="user.suspend", target_type="user",
            target_id=user_id, summary=f"suspended: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return {"suspended_at": now}


@router.post("/users/{user_id}/reactivate", summary="Reactivate a user")
async def reactivate_user(
    user_id: str,
    request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        await db.execute(
            "UPDATE users SET suspended_at = NULL, suspended_reason = NULL WHERE id = ?",
            (user_id,),
        )
        await admin_service.write_audit(
            db, actor=user, action="user.reactivate", target_type="user",
            target_id=user_id, summary="reactivated",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return {"suspended_at": None}


@router.post("/users/{user_id}/plan", summary="Change a user's plan")
async def change_plan(
    user_id: str,
    body: PlanBody,
    request: Request,
    user: dict = Depends(require_permission("billing.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        result = await admin_service.apply_plan_change(
            db, user=target, to_plan=body.plan, reason=body.reason, actor=user
        )
        await admin_service.write_audit(
            db, actor=user, action="user.plan_change", target_type="user",
            target_id=user_id,
            summary=f"plan {result['from']} -> {result['plan']}: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return result


@router.post("/users/{user_id}/trial", summary="Extend or end a user's trial")
async def change_trial(
    user_id: str,
    body: TrialBody,
    request: Request,
    user: dict = Depends(require_permission("billing.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        result = await admin_service.apply_trial_change(
            db, user=target, days=body.days, reason=body.reason, actor=user
        )
        await admin_service.write_audit(
            db, actor=user, action="user.trial_change", target_type="user",
            target_id=user_id,
            summary=f"trial days={body.days}: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return result


@router.post("/users/{user_id}/send-reset", summary="Trigger a password-reset email")
async def send_reset(
    user_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        ip = request.client.host if request.client else "admin"
        raw_token = await password_reset_service.create_reset_token(db, user_id, ip)
        await admin_service.write_audit(
            db, actor=user, action="user.send_reset", target_type="user",
            target_id=user_id, summary="password reset email sent",
        )
        await db.commit()
        email = target["email"]
    background_tasks.add_task(deliver_password_reset_email, email, raw_token)
    return {"message": "Reset email sent."}


@router.post("/users/{user_id}/send-welcome", summary="Resend the welcome email")
async def send_welcome(
    user_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        email = target["email"]
    background_tasks.add_task(deliver_welcome_email, user_id, email)
    async with get_db() as db:
        await admin_service.write_audit(
            db, actor=user, action="user.send_welcome", target_type="user",
            target_id=user_id, summary="welcome email resent",
        )
        await db.commit()
    return {"message": "Welcome email sent."}


@router.delete("/users/{user_id}", summary="Permanently delete a user (superadmin)")
async def delete_user(
    user_id: str,
    body: DeleteBody,
    request: Request,
    user: dict = Depends(require_superadmin),
):
    async with get_db() as db:
        target = await _fetch_user(db, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot delete the superadmin.")
        if body.email_confirmation.strip().lower() != (target["email"] or "").lower():
            await admin_service.write_audit(
                db, actor=user, action="user.delete_denied", target_type="user",
                target_id=user_id, summary="email confirmation mismatch",
                ip=request.client.host if request.client else None,
            )
            await db.commit()
            raise HTTPException(status_code=400, detail="Email confirmation does not match.")
        if not await verify_reauth(user, body.reauth_password, body.reauth_code or None):
            await admin_service.write_audit(
                db, actor=user, action="user.delete_denied", target_type="user",
                target_id=user_id, summary="re-authentication failed",
                ip=request.client.host if request.client else None,
            )
            await db.commit()
            raise HTTPException(status_code=403, detail="Re-authentication failed.")
        await admin_service.write_audit(
            db, actor=user, action="user.delete", target_type="user",
            target_id=user_id, summary=f"permanently deleted {target['email']}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await admin_service.delete_user_cascade(db, user_id)
        await db.commit()
    return {"deleted": True}
