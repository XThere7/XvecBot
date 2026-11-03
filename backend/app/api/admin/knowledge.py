"""
api/admin/knowledge.py
Platform-wide documents and website sources: status, failures, storage, and
retry/delete actions.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_permission
from ...core.database import get_db
from ...services import admin_service, document_service
from ...services.website_training_service import remove_page_chunks, sync_website_source
from ...services.workspace_training_service import train_workspace_document

router = APIRouter()

KNOWLEDGE_SORTABLE = {"created_at", "status", "size_bytes", "filename"}


class ReasonBody(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.get("/knowledge/documents", summary="List documents across tenants")
async def list_documents(
    search: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    direction: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("knowledge.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("(d.filename LIKE ? OR u.email LIKE ?)")
            params += [like, like]
        if status and status in (
            "uploaded", "processing", "ready", "failed", "indexing",
        ):
            where.append("d.status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        base = (
            "FROM workspace_documents d "
            "JOIN workspaces w ON w.id = d.workspace_id "
            "JOIN users u ON u.id = w.owner_id "
        )
        cur = await db.execute(f"SELECT COUNT(*) AS n {base} {clause}", tuple(params))
        total = int((await cur.fetchone())["n"])
        order_by = admin_service.validate_sort(sort, KNOWLEDGE_SORTABLE, "created_at")
        direction_sql = admin_service.validate_direction(direction)
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT d.id, d.filename, d.file_type, d.status, d.size_bytes, "
            f"d.chunk_count, d.created_at, d.workspace_id, u.email AS owner_email "
            f"{base} {clause} ORDER BY d.{order_by} {direction_sql} LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }


@router.get("/knowledge/websites", summary="List website sources across tenants")
async def list_websites(
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("knowledge.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("(s.url LIKE ? OR u.email LIKE ?)")
            params += [like, like]
        if status:
            where.append("s.status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        base = (
            "FROM website_sources s "
            "JOIN workspaces w ON w.id = s.workspace_id "
            "JOIN users u ON u.id = w.owner_id "
        )
        cur = await db.execute(f"SELECT COUNT(*) AS n {base} {clause}", tuple(params))
        total = int((await cur.fetchone())["n"])
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT s.id, s.url, s.name, s.status, s.pages_indexed, "
            f"s.pages_discovered, s.error_message, s.last_synced_at, s.created_at, "
            f"s.workspace_id, u.email AS owner_email "
            f"{base} {clause} ORDER BY s.created_at DESC LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }


@router.post("/knowledge/documents/{doc_id}/retry", summary="Retry a failed training")
async def retry_training(
    doc_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_permission("knowledge.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM workspace_documents WHERE id = ?", (doc_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        doc = dict(row)
        await db.execute(
            "UPDATE workspace_documents SET status = 'processing' WHERE id = ?",
            (doc_id,),
        )
        await admin_service.write_audit(
            db, actor=user, action="knowledge.retry_training", target_type="document",
            target_id=doc_id, summary="training retried",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    background_tasks.add_task(train_workspace_document, doc_id)
    return {"status": "processing"}


@router.post("/knowledge/websites/{source_id}/retry", summary="Retry a website sync")
async def retry_sync(
    source_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_permission("knowledge.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, status FROM website_sources WHERE id = ?", (source_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Website source not found.")
        await db.execute(
            "UPDATE website_sources SET status = 'pending', error_message = NULL "
            "WHERE id = ?",
            (source_id,),
        )
        await admin_service.write_audit(
            db, actor=user, action="knowledge.retry_sync", target_type="website_source",
            target_id=source_id, summary="sync retried",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    background_tasks.add_task(sync_website_source, source_id)
    return {"status": "pending"}


@router.delete("/knowledge/documents/{doc_id}", summary="Delete a document")
async def delete_document_admin(
    doc_id: str,
    request: Request,
    user: dict = Depends(require_permission("knowledge.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT workspace_id FROM workspace_documents WHERE id = ?", (doc_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        workspace_id = row["workspace_id"]
        await document_service.delete_document_with_data(db, doc_id=doc_id)
        await admin_service.write_audit(
            db, actor=user, action="knowledge.delete_document", target_type="document",
            target_id=doc_id, summary="deleted",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"deleted": True}


@router.delete("/knowledge/websites/{source_id}", summary="Delete a website source")
async def delete_website_admin(
    source_id: str,
    request: Request,
    user: dict = Depends(require_permission("knowledge.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT workspace_id, status FROM website_sources WHERE id = ?",
            (source_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Website source not found.")
        if row["status"] in ("running", "pending", "syncing"):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a source while it is syncing.",
            )
        async with db.execute(
            "SELECT id FROM website_pages WHERE source_id = ? AND workspace_id = ?",
            (source_id, row["workspace_id"]),
        ) as cur:
            pages = [dict(p) for p in await cur.fetchall()]
        for page in pages:
            await remove_page_chunks(db, page["id"], row["workspace_id"])
        await db.execute(
            "DELETE FROM website_pages WHERE source_id = ?", (source_id,)
        )
        await db.execute(
            "DELETE FROM website_sync_jobs WHERE source_id = ?", (source_id,)
        )
        await db.execute(
            "DELETE FROM website_sources WHERE id = ?", (source_id,)
        )
        await admin_service.write_audit(
            db, actor=user, action="knowledge.delete_website", target_type="website_source",
            target_id=source_id, summary="deleted",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"deleted": True}
