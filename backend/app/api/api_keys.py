"""
api/api_keys.py (Phase 6 — BotBase developer platform).

Dashboard management for developer API keys — same ownership pattern as
embed_tokens.py (JWT auth, full chain verification). The FULL plaintext key
is returned exactly once at creation, with a "save now" warning; every other
representation carries key_prefix only.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.logging import get_logger
from ..services import api_key_service
from .deps import get_current_user
from .workspaces import _get_owned_workspace

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["API Key Management"])

_ONCE_WARNING = "Save this key now. It will not be shown again."


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
    )


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    allowed_agents: Optional[list[str]] = None
    expires_at: Optional[str] = None


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    # Tri-state: omitted = keep, null = reset to all-agents, list = restrict.
    allowed_agents: Optional[list[str] | None] = Field(default="__unset__")
    is_active: Optional[int] = None


@router.post(
    "/{workspace_id}/api-keys",
    status_code=status.HTTP_201_CREATED,
    summary="Create a developer API key (full key shown once)",
)
async def create_key(
    workspace_id: str,
    payload: ApiKeyCreate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        record, full_key = await api_key_service.create_api_key(
            db,
            user_id=user["id"],
            workspace_id=workspace_id,
            name=payload.name,
            allowed_agents=payload.allowed_agents,
            expires_at=payload.expires_at,
        )
    log.info("Developer API key issued", workspace_id=workspace_id)
    return {**record, "key": full_key, "warning": _ONCE_WARNING}


@router.get(
    "/{workspace_id}/api-keys",
    summary="List developer API keys (prefix only)",
)
async def list_keys(
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
        return await api_key_service.get_api_keys_for_workspace(
            db, workspace_id, user["id"]
        )


@router.get(
    "/{workspace_id}/api-keys/{key_id}",
    summary="Get one API key (prefix only)",
)
async def get_key(
    workspace_id: str,
    key_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        try:
            return await api_key_service.get_api_key(db, key_id, user["id"])
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise _not_found()
            raise


@router.put(
    "/{workspace_id}/api-keys/{key_id}",
    summary="Update an API key (rename, restrict, revoke)",
)
async def update_key(
    workspace_id: str,
    key_id: str,
    payload: ApiKeyUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        fields = payload.model_dump(exclude_unset=True)
        try:
            return await api_key_service.update_api_key(
                db,
                key_id,
                user["id"],
                name=fields.get("name"),
                allowed_agents=fields.get("allowed_agents", "__unset__"),
                is_active=fields.get("is_active"),
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise _not_found()
            raise


@router.delete(
    "/{workspace_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key",
)
async def delete_key(
    workspace_id: str,
    key_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        try:
            await api_key_service.delete_api_key(db, key_id, user["id"])
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise _not_found()
            raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
