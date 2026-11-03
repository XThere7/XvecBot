"""
api/websites.py

Website-to-Knowledge API. Every route verifies the full ownership chain:
source -> workspace -> authenticated owner.

The crawl itself runs as a FastAPI BackgroundTask after the 202 response.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core import ssrf_guard
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.plan import refresh_policy_rank
from ..services import plan_service
from ..services.website_crawler import normalise_url
from ..services.website_training_service import (
    remove_page_chunks,
    sync_website_source,
)
from .deps import get_current_user
from .workspaces import _get_owned_workspace

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Websites"])


class WebsiteCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    name: Optional[str] = Field(default=None, max_length=100)
    refresh_policy: Literal["manual", "weekly", "daily"] = "manual"


def _source_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Website source not found",
    )


async def _get_owned_source(db, workspace_id: str, source_id: str) -> dict:
    async with db.execute(
        "SELECT * FROM website_sources WHERE id = ? AND workspace_id = ?",
        (source_id, workspace_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise _source_not_found()
    return dict(row)


def _default_name(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or "Website"


@router.post(
    "/{workspace_id}/websites",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Connect a website as a workspace knowledge source",
)
async def create_website_source(
    workspace_id: str,
    payload: WebsiteCreate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    validated = await ssrf_guard.validate_url_async(payload.url)
    url = normalise_url(validated)

    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        await plan_service.assert_can_create_website_source(db, workspace)
        await plan_service.assert_refresh_policy_allowed(
            db, workspace, payload.refresh_policy
        )

        async with db.execute(
            "SELECT id FROM website_sources WHERE workspace_id = ? AND url = ?",
            (workspace_id, url),
        ) as cur:
            if await cur.fetchone() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This website is already connected to the workspace.",
                )

        source_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        name = (payload.name or "").strip() or _default_name(url)
        try:
            await db.execute(
                """INSERT INTO website_sources
                   (id, workspace_id, url, name, status, pages_discovered,
                    pages_indexed, last_synced_at, next_sync_at, refresh_policy,
                    error_message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'syncing', 0, 0, NULL, NULL, ?,
                           NULL, ?, ?)""",
                (source_id, workspace_id, url, name, payload.refresh_policy, now, now),
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM website_sources WHERE id = ?", (source_id,)
            ) as cur:
                row = await cur.fetchone()
        except Exception:
            await db.rollback()
            async with db.execute(
                "SELECT id FROM website_sources WHERE workspace_id = ? AND url = ?",
                (workspace_id, url),
            ) as cur:
                if await cur.fetchone() is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This website is already connected to the workspace.",
                    )
            raise

    background_tasks.add_task(
        sync_website_source,
        source_id,
        triggered_by="manual",
        already_claimed=True,
    )
    log.info(
        "Website source created",
        source_id=source_id,
        workspace_id=workspace_id,
        url=url,
    )
    return dict(row)


@router.get(
    "/{workspace_id}/websites",
    summary="List website knowledge sources in a workspace",
)
async def list_website_sources(
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
        async with db.execute(
            """SELECT * FROM website_sources
               WHERE workspace_id = ? ORDER BY created_at DESC""",
            (workspace_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


@router.get(
    "/{workspace_id}/websites/{source_id}",
    summary="Get one website knowledge source",
)
async def get_website_source(
    workspace_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        source = await _get_owned_source(db, workspace_id, source_id)
    return source


@router.get(
    "/{workspace_id}/websites/{source_id}/pages",
    summary="List pages discovered for a website source",
)
async def list_website_pages(
    workspace_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        await _get_owned_source(db, workspace_id, source_id)
        async with db.execute(
            """SELECT * FROM website_pages
               WHERE source_id = ? AND workspace_id = ?
               ORDER BY CASE status
                            WHEN 'indexed' THEN 0
                            WHEN 'discovered' THEN 1
                            WHEN 'failed' THEN 2
                            ELSE 3
                        END, url""",
            (source_id, workspace_id),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


@router.post(
    "/{workspace_id}/websites/{source_id}/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-sync a website source now",
)
async def refresh_website_source(
    workspace_id: str,
    source_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        source = await _get_owned_source(db, workspace_id, source_id)

        if source["status"] == "syncing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A sync is already in progress.",
            )

        policy = source.get("refresh_policy") or "manual"
        allowed_policy = await plan_service.allowed_refresh_policy_for_workspace(
            db, workspace_id
        )
        if refresh_policy_rank(policy) > refresh_policy_rank(allowed_policy):
            # A trial may have expired while a daily/weekly source still
            # exists. Downgrade the source instead of letting it keep a
            # scheduled cadence the current plan does not include.
            policy = allowed_policy
            await db.execute(
                "UPDATE website_sources SET refresh_policy = ?, "
                "next_sync_at = NULL, updated_at = ? WHERE id = ?",
                (policy, datetime.now(timezone.utc).isoformat(), source_id),
            )
            await db.commit()
            source["refresh_policy"] = policy
        last_synced = source.get("last_synced_at")
        if policy in ("daily", "weekly") and last_synced:
            try:
                last = datetime.fromisoformat(last_synced)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except ValueError:
                last = None
            if last is not None:
                cooldown = timedelta(days=1 if policy == "daily" else 7)
                next_allowed = last + cooldown
                now = datetime.now(timezone.utc)
                if now < next_allowed:
                    retry_after = max(1, int((next_allowed - now).total_seconds()))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Next refresh available at {next_allowed.isoformat()}.",
                        headers={"Retry-After": str(retry_after)},
                    )

        now = datetime.now(timezone.utc).isoformat()
        claimed = await db.execute(
            """UPDATE website_sources
               SET status = 'syncing', updated_at = ?
               WHERE id = ? AND workspace_id = ? AND status != 'syncing'
               RETURNING id""",
            (now, source_id, workspace_id),
        )
        if await claimed.fetchone() is None:
            # Another request claimed the source after our initial status
            # check. Return the same conflict the check would have raised.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A sync is already in progress.",
            )
        await db.commit()

    background_tasks.add_task(
        sync_website_source,
        source_id,
        triggered_by="manual",
        already_claimed=True,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"message": "Refresh started."},
    )


@router.get(
    "/{workspace_id}/websites/{source_id}/history",
    summary="Recent sync jobs for a website source",
)
async def website_sync_history(
    workspace_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        await _get_owned_source(db, workspace_id, source_id)
        async with db.execute(
            """SELECT * FROM website_sync_jobs
               WHERE source_id = ? AND workspace_id = ?
               ORDER BY started_at DESC LIMIT 20""",
            (source_id, workspace_id),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


@router.delete(
    "/{workspace_id}/websites/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect a website source and delete its index",
)
async def delete_website_source(
    workspace_id: str,
    source_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        source = await _get_owned_source(db, workspace_id, source_id)
        if source["status"] == "syncing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete a source while it is syncing.",
            )

        async with db.execute(
            "SELECT id FROM website_pages WHERE source_id = ? AND workspace_id = ?",
            (source_id, workspace_id),
        ) as cur:
            pages = [dict(row) for row in await cur.fetchall()]

        for page in pages:
            await remove_page_chunks(db, page["id"], workspace_id)

        await db.execute(
            "DELETE FROM website_pages WHERE source_id = ? AND workspace_id = ?",
            (source_id, workspace_id),
        )
        await db.execute(
            "DELETE FROM website_sync_jobs WHERE source_id = ? AND workspace_id = ?",
            (source_id, workspace_id),
        )
        await db.execute(
            "DELETE FROM website_sources WHERE id = ? AND workspace_id = ?",
            (source_id, workspace_id),
        )
        await db.commit()

    log.info(
        "Website source deleted",
        source_id=source_id,
        workspace_id=workspace_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
