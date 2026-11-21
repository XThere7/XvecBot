"""
api/engagement.py
Dashboard API for Agent Actions, Sales & Lead Generation, Data Collection,
Custom Forms and Customer Support escalation.

Every route verifies agent -> workspace -> authenticated owner. Plan gates live
in the service layer (``require_feature`` / ``action_service.upsert_action``),
so the API cannot be used to bypass a Free-plan restriction.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..models.engagement import (
    AgentActionUpdate,
    CustomFormCreate,
    CustomFormUpdate,
    DataCollectionCreate,
    DataCollectionUpdate,
    SupportEscalationUpdate,
)
from ..services import (
    action_service,
    admin_service,
    capture_service,
    lead_service,
    support_service,
)
from .deps import get_current_user
from .workspaces import _get_owned_workspace

router = APIRouter(prefix="/workspaces", tags=["Agent Actions"])


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
    return workspace


# ── Action catalogue / configuration ─────────────────────────────────────────


@router.get(
    "/{workspace_id}/agents/{agent_id}/actions",
    summary="List action catalogue and this agent's configuration",
)
async def list_actions(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        return await action_service.catalog_for_agent(db, workspace, agent_id)


@router.put(
    "/{workspace_id}/agents/{agent_id}/actions/{action_type}",
    summary="Create or update one agent action",
)
async def upsert_action(
    workspace_id: str,
    agent_id: str,
    action_type: str,
    payload: AgentActionUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        return await action_service.upsert_action(
            db,
            workspace,
            agent_id,
            payload,
            action_type=action_type,
        )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/actions/{action_type}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one agent action",
)
async def delete_action(
    workspace_id: str,
    agent_id: str,
    action_type: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await action_service.delete_action(db, workspace_id, agent_id, action_type)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspace_id}/agents/{agent_id}/actions/{action_id}/form",
    summary="Field definition for testing an action in the dashboard",
)
async def action_form(
    workspace_id: str,
    agent_id: str,
    action_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        actions = await action_service.list_actions(db, workspace_id, agent_id)
        action = next((a for a in actions if a["id"] == action_id), None)
        if action is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Action not found"
            )
        config = action.get("config") or {}
        fields = config.get("fields") or []
        title = action.get("name") or action_type_title(action["action_type"])
        description = action.get("description") or ""
        require_consent = bool(config.get("require_consent"))

        if action["action_type"] == "custom_forms":
            forms = await capture_service.list_forms(
                db, workspace_id, agent_id, active_only=True
            )
            form = next(
                (f for f in forms if f["id"] == config.get("form_id")),
                forms[0] if forms else None,
            )
            if form is not None:
                fields = form["fields"]
                title = form["title"]
                description = form.get("description") or ""
                require_consent = bool(form.get("require_consent"))
        elif action["action_type"] == "data_collection":
            collections = await capture_service.list_collections(
                db, workspace_id, agent_id, active_only=True
            )
            collection = next(
                (c for c in collections if c["id"] == config.get("collection_id")),
                collections[0] if collections else None,
            )
            if collection is not None:
                fields = collection["fields"]
                title = collection["name"]
                description = collection.get("description") or ""
                require_consent = bool(collection.get("require_consent"))

        if action["action_type"] == "knowledge_support":
            fields = [
                {"key": "contact_name", "label": "Your name", "type": "short_text", "required": False},
                {"key": "contact_email", "label": "Email", "type": "email", "required": False},
                {"key": "contact_phone", "label": "Phone", "type": "phone", "required": False},
                {"key": "reason", "label": "What do you need help with?", "type": "long_text", "required": True},
            ]
            title = "Request human support"
            description = "A team member will follow up on this request."
            require_consent = False

        return {
            "action_id": action["id"],
            "action_type": action["action_type"],
            "title": title,
            "description": description,
            "fields": fields,
            "require_consent": require_consent,
            "consent_text": config.get("consent_text"),
            "submit_label": "Test action",
        }


class ActionFormSubmit(BaseModel):
    data: dict = Field(default_factory=dict)
    conversation_id: Optional[str] = None


@router.post(
    "/{workspace_id}/agents/{agent_id}/actions/{action_id}/submit",
    summary="Submit an interactive action form from the dashboard chat",
)
async def submit_action(
    workspace_id: str,
    agent_id: str,
    action_id: str,
    payload: ActionFormSubmit,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        return await action_service.submit_action_form(
            db,
            workspace,
            agent_id,
            action_id,
            payload.data,
            payload.conversation_id,
        )


# ── Leads ────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/agents/{agent_id}/leads",
    summary="List captured leads",
)
async def list_leads(
    workspace_id: str,
    agent_id: str,
    search: Optional[str] = Query(default=None, max_length=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await lead_service.list_leads(
            db,
            workspace_id,
            agent_id,
            search=search,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        stats = await lead_service.lead_stats(db, workspace_id, agent_id)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "stats": stats,
    }


@router.get(
    "/{workspace_id}/agents/{agent_id}/leads/export",
    summary="Export leads as CSV",
)
async def export_leads(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        csv_text = await lead_service.export_leads_csv(db, workspace_id, agent_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/leads/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lead",
)
async def delete_lead(
    workspace_id: str,
    agent_id: str,
    lead_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await lead_service.get_lead(db, workspace_id, agent_id, lead_id)
        await lead_service.delete_lead(db, workspace_id, agent_id, lead_id)
        await admin_service.write_audit(
            db,
            actor=user,
            action="lead.deleted",
            target_type="lead",
            target_id=lead_id,
            summary="Workspace owner deleted a captured lead.",
        )
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Data collections ─────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/agents/{agent_id}/collections",
    summary="List data collections",
)
async def list_collections(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await capture_service.list_collections(db, workspace_id, agent_id)


@router.post(
    "/{workspace_id}/agents/{agent_id}/collections",
    status_code=status.HTTP_201_CREATED,
    summary="Create a data collection",
)
async def create_collection(
    workspace_id: str,
    agent_id: str,
    payload: DataCollectionCreate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        await action_service._require_feature_for_actions(db, workspace)
        return await capture_service.create_collection(
            db, workspace_id, agent_id, payload
        )


@router.put(
    "/{workspace_id}/agents/{agent_id}/collections/{collection_id}",
    summary="Update a data collection",
)
async def update_collection(
    workspace_id: str,
    agent_id: str,
    collection_id: str,
    payload: DataCollectionUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        await action_service._require_feature_for_actions(db, workspace)
        return await capture_service.update_collection(
            db, workspace_id, agent_id, collection_id, payload
        )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a data collection and its submissions",
)
async def delete_collection(
    workspace_id: str,
    agent_id: str,
    collection_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await capture_service.delete_collection(
            db, workspace_id, agent_id, collection_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspace_id}/agents/{agent_id}/collections/{collection_id}/submissions",
    summary="List submissions for a collection",
)
async def list_collection_submissions(
    workspace_id: str,
    agent_id: str,
    collection_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await capture_service.list_submissions(
            db,
            workspace_id,
            agent_id,
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/{workspace_id}/agents/{agent_id}/collections/{collection_id}/export",
    summary="Export a collection's submissions as CSV",
)
async def export_collection(
    workspace_id: str,
    agent_id: str,
    collection_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        csv_text = await capture_service.export_collection_csv(
            db, workspace_id, agent_id, collection_id
        )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="collection.csv"'},
    )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a data submission",
)
async def delete_submission(
    workspace_id: str,
    agent_id: str,
    submission_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await capture_service.delete_submission(
            db, workspace_id, agent_id, submission_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Custom forms ─────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/agents/{agent_id}/forms",
    summary="List custom forms",
)
async def list_forms(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await capture_service.list_forms(db, workspace_id, agent_id)


@router.post(
    "/{workspace_id}/agents/{agent_id}/forms",
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom form",
)
async def create_form(
    workspace_id: str,
    agent_id: str,
    payload: CustomFormCreate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        await action_service._require_feature_for_actions(db, workspace)
        return await capture_service.create_form(
            db, workspace_id, agent_id, payload
        )


@router.put(
    "/{workspace_id}/agents/{agent_id}/forms/{form_id}",
    summary="Update a custom form",
)
async def update_form(
    workspace_id: str,
    agent_id: str,
    form_id: str,
    payload: CustomFormUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_scope(db, workspace_id, agent_id, user)
        await action_service._require_feature_for_actions(db, workspace)
        return await capture_service.update_form(
            db, workspace_id, agent_id, form_id, payload
        )


@router.delete(
    "/{workspace_id}/agents/{agent_id}/forms/{form_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom form and its submissions",
)
async def delete_form(
    workspace_id: str,
    agent_id: str,
    form_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        await capture_service.delete_form(db, workspace_id, agent_id, form_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspace_id}/agents/{agent_id}/forms/{form_id}/submissions",
    summary="List submissions for a form",
)
async def list_form_submissions(
    workspace_id: str,
    agent_id: str,
    form_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await capture_service.list_form_submissions(
            db,
            workspace_id,
            agent_id,
            form_id=form_id,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/{workspace_id}/agents/{agent_id}/forms/{form_id}/export",
    summary="Export a form's submissions as CSV",
)
async def export_form(
    workspace_id: str,
    agent_id: str,
    form_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        csv_text = await capture_service.export_form_csv(
            db, workspace_id, agent_id, form_id
        )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="form-submissions.csv"'},
    )


# ── Support escalations ──────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/agents/{agent_id}/escalations",
    summary="List support escalations",
)
async def list_escalations(
    workspace_id: str,
    agent_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        items, total = await support_service.list_escalations(
            db,
            workspace_id,
            agent_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        stats = await support_service.stats(db, workspace_id, agent_id)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "stats": stats,
    }


@router.put(
    "/{workspace_id}/agents/{agent_id}/escalations/{escalation_id}",
    summary="Update an escalation's status",
)
async def update_escalation(
    workspace_id: str,
    agent_id: str,
    escalation_id: str,
    payload: SupportEscalationUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_scope(db, workspace_id, agent_id, user)
        return await support_service.update_status(
            db, workspace_id, agent_id, escalation_id, payload.status
        )


def action_type_title(action_type: str) -> str:
    return action_service.ACTION_CATALOG.get(action_type, {}).get("name", action_type)
