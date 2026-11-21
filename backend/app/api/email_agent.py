"""
api/email_agent.py
Email Agent dashboard API.

Security boundaries:
  * every route verifies agent -> workspace -> owner;
  * credentials are write-only (stored encrypted, never returned);
  * sending is simulated and requires an explicit confirmation flag;
  * integration changes, approvals and rejections are written to the
    append-only audit log.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..core.database import get_db
from ..models.email_agent import (
    EmailApprovalRequest,
    EmailDraftUpdate,
    EmailIntegrationUpsert,
    EmailRejectRequest,
    SimulatedEmailRequest,
)
from ..services import email_agent_service, notification_service
from .deps import get_current_user
from .workspaces import _get_owned_workspace

router = APIRouter(prefix="/workspaces", tags=["Email Agent"])


async def _require_scope(db, workspace_id: str, agent_id: str, user: dict) -> dict:
    workspace = await _get_owned_workspace(db, workspace_id, user["id"])
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    async with db.execute(
        "SELECT * FROM agents WHERE id = ? AND workspace_id = ?",
        (agent_id, workspace_id),
    ) as cur:
        agent = await cur.fetchone()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return {"workspace": workspace, "agent": dict(agent)}


@router.get(
    "/{workspace_id}/agents/{agent_id}/email",
    summary="Get this agent's mailbox configuration",
)
async def get_email_integration(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        integration = await email_agent_service.get_integration(
            db, workspace_id, agent_id
        )
        stats = await email_agent_service.stats(db, workspace_id, agent_id)
        notifications = await notification_service.list_notifications(
            db, workspace_id, agent_id
        )
    return {
        "integration": integration,
        "stats": stats,
        "notifications": notifications,
        "sending_mode": "simulated",
        "sms_mode": "simulated",
    }


@router.put(
    "/{workspace_id}/agents/{agent_id}/email",
    summary="Create or update the mailbox configuration",
)
async def upsert_email_integration(
    workspace_id: str,
    agent_id: str,
    payload: EmailIntegrationUpsert,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        scope = await _require_scope(db, workspace_id, agent_id, user)
        return await email_agent_service.upsert_integration(
            db,
            scope["workspace"],
            agent_id,
            payload,
            actor=user,
        )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the mailbox configuration and stored credentials",
)
async def delete_email_integration(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await email_agent_service.delete_integration(
            db, workspace_id, agent_id, actor=user
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/agents/{agent_id}/email/simulate",
    status_code=status.HTTP_201_CREATED,
    summary="Deliver a simulated inbound email and generate an AI draft",
)
async def simulate_incoming_email(
    workspace_id: str,
    agent_id: str,
    payload: SimulatedEmailRequest,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        scope = await _require_scope(db, workspace_id, agent_id, user)
        result = await email_agent_service.receive_email(
            db,
            scope["workspace"],
            scope["agent"],
            payload,
            actor=user,
        )
    if result.get("duplicate"):
        return result
    return result


@router.get(
    "/{workspace_id}/agents/{agent_id}/email/drafts",
    summary="List email drafts",
)
async def list_drafts(
    workspace_id: str,
    agent_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await email_agent_service.list_drafts(
            db,
            workspace_id,
            agent_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/{workspace_id}/agents/{agent_id}/email/drafts/{draft_id}",
    summary="Get one draft and its source email",
)
async def get_draft(
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await email_agent_service.get_draft(db, workspace_id, agent_id, draft_id)


@router.put(
    "/{workspace_id}/agents/{agent_id}/email/drafts/{draft_id}",
    summary="Edit a draft before approval",
)
async def update_draft(
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    payload: EmailDraftUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await email_agent_service.update_draft(
            db, workspace_id, agent_id, draft_id, payload.body, actor=user
        )


@router.post(
    "/{workspace_id}/agents/{agent_id}/email/drafts/{draft_id}/approve",
    summary="Approve a draft and simulate sending it",
)
async def approve_draft(
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    payload: EmailApprovalRequest,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await email_agent_service.approve_and_simulate_send(
            db,
            workspace_id,
            agent_id,
            draft_id,
            body=payload.body,
            confirm_simulated_send=payload.confirm_simulated_send,
            actor=user,
        )


@router.post(
    "/{workspace_id}/agents/{agent_id}/email/drafts/{draft_id}/reject",
    summary="Reject a draft",
)
async def reject_draft(
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    payload: EmailRejectRequest,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await email_agent_service.reject_draft(
            db, workspace_id, agent_id, draft_id, reason=payload.reason, actor=user
        )


@router.get(
    "/{workspace_id}/agents/{agent_id}/email/incoming",
    summary="List received emails",
)
async def list_incoming(
    workspace_id: str,
    agent_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await email_agent_service.list_incoming(
            db, workspace_id, agent_id, limit=limit, offset=offset
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/{workspace_id}/agents/{agent_id}/email/notifications",
    summary="List simulated SMS notifications",
)
async def list_notifications(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items = await notification_service.list_notifications(
            db, workspace_id, agent_id
        )
    return {"items": items, "sms_mode": "simulated"}


@router.get(
    "/{workspace_id}/agents/{agent_id}/email/audit",
    summary="Recent email-agent audit entries for this workspace",
)
async def email_audit(
    workspace_id: str,
    agent_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        # Audit rows have no workspace column, so constrain by the ids that
        # belong to this agent. Never query the global log unfiltered.
        async with db.execute(
            """SELECT id FROM email_drafts
               WHERE workspace_id = ? AND agent_id = ?
               ORDER BY created_at DESC LIMIT 100""",
            (workspace_id, agent_id),
        ) as cur:
            draft_ids = [row["id"] for row in await cur.fetchall()]
        async with db.execute(
            """SELECT id FROM email_integrations
               WHERE workspace_id = ? AND agent_id = ?""",
            (workspace_id, agent_id),
        ) as cur:
            integration_rows = await cur.fetchall()
        target_ids = draft_ids + [row["id"] for row in integration_rows]
        if not target_ids:
            return {"items": []}
        placeholders = ", ".join("?" for _ in target_ids)
        async with db.execute(
            f"""SELECT ts, action, target_type, target_id, summary
                FROM audit_log
                WHERE target_id IN ({placeholders})
                ORDER BY ts DESC LIMIT ?""",
            (*target_ids, limit),
        ) as cur:
            rows = await cur.fetchall()
    return {"items": [dict(r) for r in rows]}
