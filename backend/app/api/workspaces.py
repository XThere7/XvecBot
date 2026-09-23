"""
api/workspaces.py
Workspace CRUD — multi-tenant, every route scoped to the authenticated owner.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..core.database import get_db
from ..core.logging import get_logger
from ..models.workspace import WorkspaceCreate, WorkspaceUpdate
from ..storage import vector_store
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
    async with get_db() as db:
        await db.execute(
            """INSERT INTO workspaces (id, name, description, system_prompt, owner_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                workspace_id,
                payload.name,
                payload.description,
                payload.system_prompt,
                user["id"],
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

        await vector_store.delete_by_workspace(db, workspace_id)
        await db.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,)
        )
        await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        await db.commit()

    log.info("Workspace deleted", workspace_id=workspace_id, owner_id=user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
