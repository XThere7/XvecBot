"""
api/billing.py
Subscription catalogue and per-workspace plan/usage endpoints.

Payments are intentionally not wired up yet. New accounts start on a 21-day
Pro trial and fall back to Free; existing paid workspace overrides are
preserved. The catalogue is public so the pricing page can render the real
limits, and the plan-change endpoint refuses paid changes with a clear 503.
Operators can move a workspace for testing with `scripts/set_plan.py`.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.plan import TRIAL_DAYS
from ..core.plans import LAUNCH_NOTE, PLAN_CATALOG, get_plan, plan_list
from ..services import plan_service
from .deps import get_current_user
from .workspaces import _get_owned_workspace

router = APIRouter(tags=["Billing"])


def _plans_payload() -> dict:
    """Shared public catalogue used by /plans and /billing/plans."""
    return {
        "currency": "TZS",
        "plans": [plan.as_dict() for plan in plan_list()],
        "trial": {
            "duration_days": TRIAL_DAYS,
            "description": (
                "All new accounts include a 21-day free trial with full Pro "
                "access. No credit card required."
            ),
            "limits": get_plan("trial").limits,
        },
        "payments_configured": False,
        "upgrade_available": False,
        "launch_note": LAUNCH_NOTE,
    }


@router.get(
    "/plans",
    summary="Subscription plans, TZS prices and 21-day trial (public)",
)
async def public_plans():
    """The public pricing contract rendered by the marketing page."""
    return _plans_payload()


@router.get(
    "/billing/plans",
    summary="Subscription plans and limits (public)",
)
async def list_plans():
    """The canonical plan catalogue — the pricing page renders this verbatim."""
    return _plans_payload()


@router.get(
    "/workspaces/{workspace_id}/billing",
    summary="Current plan, usage and monthly reset date",
)
async def get_billing(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        return await plan_service.billing_summary(db, workspace)


class ChangePlanRequest(BaseModel):
    plan: str = Field(..., min_length=1, max_length=32)


@router.post(
    "/workspaces/{workspace_id}/billing/plan",
    summary="Request a plan change (paid upgrades are not live yet)",
)
async def change_plan(
    workspace_id: str,
    payload: ChangePlanRequest,
    user: dict = Depends(get_current_user),
):
    requested = payload.plan.strip().lower()
    if requested not in PLAN_CATALOG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown plan '{payload.plan}'.",
        )

    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        # Idempotent no-op: asking for the plan you already have is harmless.
        if (workspace.get("plan") or "free") == requested:
            return await plan_service.billing_summary(db, workspace)

    # Deliberately no self-service upgrade path while no payment provider is
    # configured. This prevents the public API from handing out paid plans.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "payments_not_configured",
            "message": (
                "Paid plans are not available yet because payments are not "
                "configured. New accounts use the 21-day trial, then Free."
            ),
            "requested_plan": requested,
            "payments_configured": False,
        },
    )
