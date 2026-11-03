"""
api/admin/subscriptions.py
Subscriptions and billing: plans with trial state, plan-change history,
manual payment recording, upcoming expiries.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_permission
from ...core.database import get_db
from ...core.plan import PLAN_IDS
from ...services import admin_service

router = APIRouter()

PAYMENT_METHODS = {"mpesa", "tigo", "airtel", "bank", "cash", "other"}


class PlanBody(BaseModel):
    plan: str = Field(..., min_length=1, max_length=20)
    reason: str = Field(default="", max_length=500)


class TrialBody(BaseModel):
    days: int = Field(..., ge=-1, le=365)
    reason: str = Field(default="", max_length=500)


class PaymentBody(BaseModel):
    amount_tzs: int = Field(..., gt=0, le=10_000_000_000)
    method: str = Field(..., min_length=1, max_length=20)
    reference: str = Field(default="", max_length=200)
    period_start: str = Field(default="", max_length=64)
    period_end: str = Field(default="", max_length=64)


@router.get("/subscriptions", summary="Plans, trials and upcoming expiries")
async def subscriptions(
    search: str | None = None,
    plan: str | None = None,
    trial: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("billing.read")),
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
        now = datetime.now(timezone.utc).isoformat()
        if trial == "active":
            where.append("trial_ends_at > ?")
            params.append(now)
        elif trial == "expired":
            where.append("trial_ends_at IS NOT NULL AND trial_ends_at <= ?")
            params.append(now)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur = await db.execute(
            f"SELECT COUNT(*) AS n FROM users {clause}", tuple(params)
        )
        total = int((await cur.fetchone())["n"])
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT id, email, plan, trial_ends_at, created_at, suspended_at "
            f"FROM users {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
        expiring = await db.execute(
            "SELECT id, email, trial_ends_at FROM users "
            "WHERE trial_ends_at IS NOT NULL AND trial_ends_at > ? "
            "ORDER BY trial_ends_at ASC LIMIT 50",
            (now,),
        )
        expiring_rows = await expiring.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
        "upcoming_expiries": [dict(r) for r in expiring_rows],
    }


@router.get("/subscriptions/{user_id}/history", summary="Plan-change history")
async def plan_history(
    user_id: str,
    user: dict = Depends(require_permission("billing.read")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, from_plan, to_plan, reason, changed_by, changed_at "
            "FROM plan_changes WHERE user_id = ? ORDER BY changed_at DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/subscriptions/{user_id}/plan", summary="Manual plan change")
async def change_plan(
    user_id: str,
    body: PlanBody,
    request: Request,
    user: dict = Depends(require_permission("billing.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, plan FROM users WHERE id = ?", (user_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        result = await admin_service.apply_plan_change(
            db, user=dict(target), to_plan=body.plan, reason=body.reason, actor=user
        )
        await admin_service.write_audit(
            db, actor=user, action="billing.plan_change", target_type="user",
            target_id=user_id,
            summary=f"plan {result['from']} -> {result['plan']}: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return result


@router.post("/subscriptions/{user_id}/trial", summary="Extend or end a trial")
async def change_trial(
    user_id: str,
    body: TrialBody,
    request: Request,
    user: dict = Depends(require_permission("billing.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, trial_ends_at FROM users WHERE id = ?", (user_id,)
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        result = await admin_service.apply_trial_change(
            db, user=dict(target), days=body.days, reason=body.reason, actor=user
        )
        await admin_service.write_audit(
            db, actor=user, action="billing.trial_change", target_type="user",
            target_id=user_id, summary=f"trial days={body.days}: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return result


@router.post("/payments/{user_id}", summary="Record a manual payment")
async def record_payment(
    user_id: str,
    body: PaymentBody,
    request: Request,
    user: dict = Depends(require_permission("billing.manage")),
):
    if body.method.lower() not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Unknown payment method.")
    async with get_db() as db:
        cur = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="User not found.")
        payment_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO payments (id, user_id, amount_tzs, method, reference, "
            "period_start, period_end, recorded_by, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payment_id, user_id, body.amount_tzs, body.method.lower(),
                body.reference or None, body.period_start or None,
                body.period_end or None, user.get("email"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await admin_service.write_audit(
            db, actor=user, action="billing.payment_recorded", target_type="user",
            target_id=user_id,
            summary=f"payment {body.amount_tzs} TZS via {body.method.lower()}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"id": payment_id, "amount_tzs": body.amount_tzs}


@router.get("/payments", summary="List payments")
async def list_payments(
    search: str | None = None,
    method: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("billing.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("(u.email LIKE ? OR p.reference LIKE ?)")
            params += [like, like]
        if method:
            where.append("p.method = ?")
            params.append(method)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur = await db.execute(
            f"SELECT COUNT(*) AS n FROM payments p JOIN users u ON u.id = p.user_id "
            f"{clause}",
            tuple(params),
        )
        total = int((await cur.fetchone())["n"])
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT p.id, p.user_id, u.email, p.amount_tzs, p.method, p.reference, "
            f"p.period_start, p.period_end, p.recorded_by, p.recorded_at "
            f"FROM payments p JOIN users u ON u.id = p.user_id {clause} "
            f"ORDER BY p.recorded_at DESC LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }
