"""
api/workspaces.py
Workspace CRUD — multi-tenant, every route scoped to the authenticated owner.
"""
import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.plans import get_plan
from ..models.workspace import WorkspaceCreate, WorkspaceUpdate
from ..storage import vector_store
from ..storage.object_store import get_storage
from .deps import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


async def _get_owned_workspace(db, workspace_id: str, owner_id: str) -> Optional[dict]:
    """Return the workspace as a dict, or None if missing or owned by someone else."""
    async with db.execute(
        "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or row["owner_id"] != owner_id:
        return None
    return dict(row)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create_workspace(
    payload: WorkspaceCreate,
    user: dict = Depends(get_current_user),
):
    workspace_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Resolve the launch default through the catalogue so an invalid env value
    # can never put a workspace on a plan the rest of the app does not know.
    initial_plan = get_plan(settings.default_workspace_plan)
    async with get_db() as db:
        await db.execute(
            """INSERT INTO workspaces
               (id, name, description, system_prompt, owner_id, created_at,
                plan, plan_started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workspace_id,
                payload.name,
                payload.description,
                payload.system_prompt,
                user["id"],
                now,
                initial_plan.id,
                now,
            ),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ) as cur:
            row = await cur.fetchone()

    log.info("Workspace created", workspace_id=workspace_id, owner_id=user["id"])
    return dict(row)


@router.get(
    "",
    summary="List my workspaces",
)
async def list_workspaces(user: dict = Depends(get_current_user)):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM workspaces WHERE owner_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get(
    "/{workspace_id}",
    summary="Get a workspace by ID",
)
async def get_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
    if workspace is None:
        raise _not_found()
    return workspace


@router.put(
    "/{workspace_id}",
    summary="Update a workspace (partial)",
)
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    user: dict = Depends(get_current_user),
):
    updates = payload.model_dump(exclude_unset=True)
    async with get_db() as db:
        current = await _get_owned_workspace(db, workspace_id, user["id"])
        if current is None:
            raise _not_found()

        current.update(updates)
        await db.execute(
            "UPDATE workspaces SET name = ?, description = ?, system_prompt = ? WHERE id = ?",
            (current["name"], current["description"], current["system_prompt"], workspace_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ) as cur:
            row = await cur.fetchone()

    log.info("Workspace updated", workspace_id=workspace_id, fields=sorted(updates))
    return dict(row)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace and all its data",
)
async def delete_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise _not_found()

        # Collect stored bytes locations BEFORE row deletes (Phase 2: fix the
        # orphan bug — local files and R2/S3 objects are removed too).
        async with db.execute(
            "SELECT * FROM workspace_documents "
            "WHERE workspace_id = ? AND file_type NOT IN ('website', 'social')",
            (workspace_id,),
        ) as cur:
            doc_rows = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT id FROM agents WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            agent_ids = [r["id"] for r in await cur.fetchall()]

        # Delete the vector index first: it resolves chunk ids while the
        # chunk/document rows still exist. Then remove every row owned by this
        # workspace explicitly instead of depending on SQLite cascade quirks
        # (the agent_id column was added to pre-existing databases by ALTER).
        await vector_store.delete_by_workspace(db, workspace_id)

        await db.execute(
            """DELETE FROM chunks
               WHERE workspace_id = ?
                  OR doc_id IN (
                      SELECT id FROM workspace_documents WHERE workspace_id = ?
                  )
                  OR document_id IN (
                      SELECT id FROM workspace_documents WHERE workspace_id = ?
                  )""",
            (workspace_id, workspace_id, workspace_id),
        )
        await db.execute(
            """DELETE FROM documents
               WHERE id IN (
                   SELECT id FROM workspace_documents WHERE workspace_id = ?
               )""",
            (workspace_id,),
        )
        await db.execute(
            """DELETE FROM messages
               WHERE conversation_id IN (
                   SELECT id FROM conversations
                   WHERE agent_id IN (
                       SELECT id FROM agents WHERE workspace_id = ?
                   )
               )""",
            (workspace_id,),
        )
        await db.execute(
            """DELETE FROM conversations
               WHERE agent_id IN (
                   SELECT id FROM agents WHERE workspace_id = ?
               )""",
            (workspace_id,),
        )
        # Transcripts that are not agent-linked but quote this workspace's
        # documents (legacy /api/v1/query) carry the workspace id directly.
        await db.execute(
            """DELETE FROM messages
               WHERE conversation_id IN (
                   SELECT id FROM conversations WHERE workspace_id = ?
               )""",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM conversations WHERE workspace_id = ?",
            (workspace_id,),
        )
        await db.execute(
            """DELETE FROM agent_embed_tokens
               WHERE agent_id IN (
                   SELECT id FROM agents WHERE workspace_id = ?
               )""",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM developer_api_keys WHERE workspace_id = ?",
            (workspace_id,),
        )
        # Subscription usage is workspace-owned; remove it with the workspace.
        await db.execute(
            "DELETE FROM usage_events WHERE workspace_id = ?", (workspace_id,)
        )
        # Website knowledge sources own pages, sync jobs, and the virtual
        # workspace_documents rows removed below.
        await db.execute(
            "DELETE FROM website_pages WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sync_jobs WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM website_sources WHERE workspace_id = ?", (workspace_id,)
        )
        # Social media sources are agent-scoped; remove them explicitly before
        # the agent rows so their virtual documents cannot outlive them.
        await db.execute(
            "DELETE FROM social_media_sources WHERE workspace_id = ?",
            (workspace_id,),
        )
        await db.execute(
            "DELETE FROM agents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        await db.commit()

    # Best-effort byte cleanup outside the transaction (never fails the delete).
    for doc in doc_rows:
        try:
            if doc.get("file_path"):
                Path(doc["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if doc.get("object_key") and settings.use_s3_storage:
                await asyncio.to_thread(
                    get_storage().delete_object, doc["object_key"]
                )
        except Exception as exc:
            log.warning(
                "Workspace object cleanup failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
    # Remove the per-workspace upload directory once its files are gone
    # (best-effort: rmdir only succeeds when empty, so unknown extra files
    # are never destroyed).
    try:
        (settings.workspace_upload_path / workspace_id).rmdir()
    except OSError:
        pass
    for agent_id in agent_ids:
        try:
            shutil.rmtree(
                settings.workspace_upload_path / "icons" / agent_id,
                ignore_errors=True,
            )
        except Exception:
            pass
    if settings.use_s3_storage:
        # Prefix sweep catches objects outside the per-row keys (defensive).
        try:
            prefix = (
                f"{settings.s3_prefix.strip().strip('/')}/workspaces/{workspace_id}"
                if settings.s3_prefix.strip()
                else f"workspaces/{workspace_id}"
            )
            await asyncio.to_thread(get_storage().delete_prefix, prefix)
        except Exception as exc:
            log.warning(
                "Workspace prefix sweep failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
    else:
        # Local backend: drop the workspace upload directory.
        try:
            shutil.rmtree(
                settings.workspace_upload_path / workspace_id, ignore_errors=True
            )
        except Exception:
            pass

    log.info("Workspace deleted", workspace_id=workspace_id, owner_id=user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
