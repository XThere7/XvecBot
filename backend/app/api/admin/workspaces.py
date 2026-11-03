"""
api/admin/workspaces.py
Cross-tenant workspace and agent management.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .deps import require_permission
from ...core.database import get_db
from ...services import admin_service

router = APIRouter()

WORKSPACES_SORTABLE = {"created_at", "name", "plan"}


class ToggleBody(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.get("/workspaces", summary="List workspaces across tenants")
async def list_workspaces(
    search: str | None = None,
    plan: str | None = None,
    sort: str | None = None,
    direction: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("workspaces.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("(w.name LIKE ? OR u.email LIKE ?)")
            params += [like, like]
        if plan and plan in ("free", "standard", "pro"):
            where.append("w.plan = ?")
            params.append(plan)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        base = (
            "FROM workspaces w JOIN users u ON u.id = w.owner_id "
            "LEFT JOIN (SELECT workspace_id, COUNT(*) AS n FROM agents GROUP BY workspace_id) a "
            "ON a.workspace_id = w.id "
            "LEFT JOIN (SELECT workspace_id, COUNT(*) AS n FROM workspace_documents GROUP BY workspace_id) d "
            "ON d.workspace_id = w.id "
            "LEFT JOIN (SELECT workspace_id, COUNT(*) AS n FROM chunks GROUP BY workspace_id) c "
            "ON c.workspace_id = w.id "
            "LEFT JOIN (SELECT workspace_id, MAX(created_at) AS last FROM usage_events GROUP BY workspace_id) ue "
            "ON ue.workspace_id = w.id "
        )
        cur = await db.execute(
            f"SELECT COUNT(*) AS n {base} {clause}", tuple(params)
        )
        total = int((await cur.fetchone())["n"])
        order_by = admin_service.validate_sort(sort, WORKSPACES_SORTABLE, "created_at")
        direction_sql = admin_service.validate_direction(direction)
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT w.id, w.name, w.plan, w.created_at, w.owner_id, u.email AS owner_email, "
            f"COALESCE(a.n,0) AS agents, COALESCE(d.n,0) AS documents, "
            f"COALESCE(c.n,0) AS chunks, ue.last AS last_activity "
            f"{base} {clause} ORDER BY w.{order_by} {direction_sql} LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }


@router.get("/workspaces/{workspace_id}", summary="Workspace detail")
async def workspace_detail(
    workspace_id: str,
    user: dict = Depends(require_permission("workspaces.read")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT w.*, u.email AS owner_email FROM workspaces w "
            "JOIN users u ON u.id = w.owner_id WHERE w.id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        detail = dict(row)
        cur = await db.execute(
            "SELECT id, name, model, is_active, created_at FROM agents "
            "WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        detail["agents"] = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute(
            "SELECT id, filename, status, size_bytes, chunk_count, created_at "
            "FROM workspace_documents WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        detail["documents"] = [dict(r) for r in await cur.fetchall()]
    return detail


@router.post("/workspaces/{workspace_id}/agents/{agent_id}/disable",
             summary="Disable an agent")
async def disable_agent(
    workspace_id: str,
    agent_id: str,
    body: ToggleBody,
    request: Request,
    user: dict = Depends(require_permission("workspaces.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Agent not found.")
        await db.execute("UPDATE agents SET is_active = 0 WHERE id = ?", (agent_id,))
        await admin_service.write_audit(
            db, actor=user, action="agent.disable", target_type="agent",
            target_id=agent_id, summary=f"disabled: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"is_active": False}


@router.post("/workspaces/{workspace_id}/agents/{agent_id}/enable",
             summary="Enable an agent")
async def enable_agent(
    workspace_id: str,
    agent_id: str,
    body: ToggleBody,
    request: Request,
    user: dict = Depends(require_permission("workspaces.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Agent not found.")
        await db.execute("UPDATE agents SET is_active = 1 WHERE id = ?", (agent_id,))
        await admin_service.write_audit(
            db, actor=user, action="agent.enable", target_type="agent",
            target_id=agent_id, summary=f"enabled: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"is_active": True}


@router.delete("/workspaces/{workspace_id}", summary="Delete a workspace")
async def delete_workspace_admin(
    workspace_id: str,
    request: Request,
    user: dict = Depends(require_permission("workspaces.manage")),
):
    from ...api.workspaces import delete_workspace as _unused  # reuse none
    from ...storage import vector_store
    from ...storage.object_store import get_storage

    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM workspaces WHERE id = ?", (workspace_id,)
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        await vector_store.delete_by_workspace(db, workspace_id)
        await db.execute(
            "DELETE FROM chunks WHERE workspace_id = ? OR doc_id IN "
            "(SELECT id FROM workspace_documents WHERE workspace_id = ?) OR "
            "document_id IN (SELECT id FROM workspace_documents WHERE workspace_id = ?)",
            (workspace_id, workspace_id, workspace_id),
        )
        await db.execute(
            "DELETE FROM documents WHERE id IN (SELECT id FROM workspace_documents WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM conversations WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM agent_embed_tokens WHERE agent_id IN (SELECT id FROM agents WHERE workspace_id = ?)",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM developer_api_keys WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM usage_events WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_pages WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sync_jobs WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sources WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM social_media_sources WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM agents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        await admin_service.write_audit(
            db, actor=user, action="workspace.delete", target_type="workspace",
            target_id=workspace_id, summary="deleted",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"deleted": True}
