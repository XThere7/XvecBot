"""
api/social_media.py

Agent-scoped public social media import API.

Every route resolves the full ownership chain
source -> agent -> workspace -> authenticated owner. The actual extraction and
indexing run as in-process background tasks, matching the website crawler.
"""
from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.logging import get_logger
from ..services import agent_service, plan_service, social_media_service
from ..services.social_media_service import (
    DuplicateMediaError,
    MediaValidationError,
)
from .deps import get_current_user
from .workspaces import _get_owned_workspace

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Social media"])


class MediaCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class MediaUpdate(BaseModel):
    content_text: str = Field(..., min_length=1, max_length=20000)
    title: Optional[str] = Field(default=None, max_length=200)


class MediaSync(BaseModel):
    source_ids: Optional[list[str]] = Field(default=None, max_length=100)


def _raise_media_error(exc: MediaValidationError) -> None:
    if isinstance(exc, DuplicateMediaError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detail(),
        )
    if exc.code == "not_found":
        code = status.HTTP_404_NOT_FOUND
    elif exc.code in {"busy", "invalid_status", "already_imported"}:
        code = status.HTTP_409_CONFLICT
    elif exc.code in {"unsupported_platform", "not_a_post"}:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=exc.message)


async def _require_agent(db, workspace_id: str, agent_id: str, user_id: str) -> dict:
    try:
        agent = await agent_service.get_agent(db, agent_id, user_id)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    if agent["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return agent


async def _require_workspace(db, workspace_id: str, user_id: str) -> dict:
    workspace = await _get_owned_workspace(db, workspace_id, user_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return workspace


async def _source_or_404(db, workspace_id: str, agent_id: str, source_id: str) -> dict:
    source = await social_media_service.get_source(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        source_id=source_id,
    )
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media source not found"
        )
    return source


@router.get(
    "/{workspace_id}/agents/{agent_id}/media",
    summary="List social media sources imported into an agent",
)
async def list_media(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        sources = await social_media_service.list_sources(
            db, workspace_id=workspace_id, agent_id=agent_id
        )
        usage = await social_media_service.media_usage(
            db, workspace=workspace, agent_id=agent_id
        )
    return {
        "sources": sources,
        "usage": usage,
        "supported_platforms": list(social_media_service.PLATFORMS),
        "max_content_chars": social_media_service.MAX_CONTENT_CHARS,
    }


@router.post(
    "/{workspace_id}/agents/{agent_id}/media",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Add a public social media link and start extraction",
)
async def create_media(
    workspace_id: str,
    agent_id: str,
    payload: MediaCreate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        await plan_service.assert_can_import_social_media(db, workspace, agent_id)
        try:
            source = await social_media_service.create_source(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                url=payload.url,
            )
        except MediaValidationError as exc:
            _raise_media_error(exc)
        usage = await social_media_service.media_usage(
            db, workspace=workspace, agent_id=agent_id
        )
    background_tasks.add_task(social_media_service.extract_source, source["id"])
    return {"source": source, "usage": usage}


@router.get(
    "/{workspace_id}/agents/{agent_id}/media/{source_id}",
    summary="Read one social media source",
)
async def get_media(
    workspace_id: str,
    agent_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        return await _source_or_404(db, workspace_id, agent_id, source_id)


@router.patch(
    "/{workspace_id}/agents/{agent_id}/media/{source_id}",
    summary="Save reviewed caption or transcript text",
)
async def update_media(
    workspace_id: str,
    agent_id: str,
    source_id: str,
    payload: MediaUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        try:
            return await social_media_service.update_source_text(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                source_id=source_id,
                content_text=payload.content_text,
                title=payload.title,
            )
        except MediaValidationError as exc:
            _raise_media_error(exc)


@router.post(
    "/{workspace_id}/agents/{agent_id}/media/{source_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry extraction or re-index a failed media source",
)
async def retry_media(
    workspace_id: str,
    agent_id: str,
    source_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        try:
            source, extraction_needed = await social_media_service.prepare_retry(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                source_id=source_id,
            )
        except MediaValidationError as exc:
            _raise_media_error(exc)
    if extraction_needed:
        background_tasks.add_task(social_media_service.extract_source, source_id)
    return source


@router.post(
    "/{workspace_id}/agents/{agent_id}/media/sync",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Sync ready media sources into the agent's knowledge",
)
async def sync_media(
    workspace_id: str,
    agent_id: str,
    payload: MediaSync,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        try:
            sources = await social_media_service.claim_sources_for_sync(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                source_ids=payload.source_ids,
            )
        except MediaValidationError as exc:
            _raise_media_error(exc)
    background_tasks.add_task(
        social_media_service.index_sources, [source["id"] for source in sources]
    )
    return {"sources": sources, "queued": len(sources)}


@router.delete(
    "/{workspace_id}/agents/{agent_id}/media/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a media source and its agent-scoped knowledge",
)
async def delete_media(
    workspace_id: str,
    agent_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_workspace(db, workspace_id, user["id"])
        await _require_agent(db, workspace_id, agent_id, user["id"])
        try:
            deleted = await social_media_service.delete_source(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                source_id=source_id,
            )
        except MediaValidationError as exc:
            _raise_media_error(exc)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media source not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
