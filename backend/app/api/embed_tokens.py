"""
api/embed_tokens.py
Dashboard API for managing agent embed tokens (Phase 4).

All endpoints require JWT auth and verify the ownership chain:
token → agent → workspace → owner_id == current_user["id"].
A broken chain raises 404 (not 403) — the platform-wide security convention.

The full token string is returned ONLY at creation (POST) and via the
JWT-protected snippet endpoint. Everywhere else it is masked.
"""
import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..models.embed_token import EmbedSnippet, EmbedTokenCreate, EmbedTokenRead, EmbedTokenUpdate
from ..services import agent_service
from .deps import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Embed Tokens"])

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

MAX_LABEL_LENGTH = 100
MASK_PREFIX = 8


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mask_token(token: str) -> str:
    """Show only the first 8 characters, then ellipsis."""
    return token[:MASK_PREFIX] + "..."


def _parse_origins(raw: Optional[str]) -> Optional[list[str]]:
    """Parse the stored JSON array back to a list. None = allow all."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, list) else None


def _serialize_origins(origins: Optional[list[str]]) -> Optional[str]:
    """Serialise a list to a JSON string. None/empty = allow all (store null)."""
    if not origins:
        return None
    return json.dumps(origins)


def _token_to_dict(row: dict, mask: bool = True) -> dict:
    """Convert a token row to the dashboard shape (origins parsed, token masked)."""
    token = row["token"]
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "token": _mask_token(token) if mask else token,
        "label": row["label"],
        "is_active": bool(row["is_active"]),
        "allowed_origins": _parse_origins(row["allowed_origins"]),
        "request_count": row["request_count"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
    }


async def _require_owned_agent(
    db,
    workspace_id: str,
    agent_id: str,
    user: dict,
) -> dict:
    """
    Verify the agent exists, belongs to the workspace, and is owned by the user.
    A broken chain raises 404 (not 403) — the platform-wide convention.
    """
    try:
        agent = await agent_service.get_agent(db, agent_id, user["id"])
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        raise
    if agent["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found in this workspace",
        )
    return agent


async def _get_owned_token(
    db,
    workspace_id: str,
    agent_id: str,
    token_id: str,
    user: dict,
) -> dict:
    """
    Verify the full ownership chain and return the token row.
    token → agent → workspace → owner. Raises 404 if any link is broken.
    """
    await _require_owned_agent(db, workspace_id, agent_id, user)

    async with db.execute(
        "SELECT * FROM agent_embed_tokens WHERE id = ?", (token_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or row["agent_id"] != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Embed token not found",
        )
    return dict(row)


def _widget_js_path() -> str:
    """
    Filename the customer snippet should point at.

    Prefers the minified production bundle, but falls back to the readable
    source when the bundle has not been built (fresh clone, dev machine), so a
    snippet is never handed a 404 URL. Set WIDGET_MINIFIED=false to always
    serve the readable source.
    """
    bundle = _STATIC_DIR / "widget.min.js"
    if settings.widget_minified and bundle.is_file():
        return "widget.min.js"
    return "widget.js"


def _build_snippet(token: str) -> str:
    """Ready-to-paste HTML snippet for embedding the widget."""
    base = settings.app_public_url.rstrip("/")
    return (
        "<!-- XvecBot chat widget -->\n"
        f'<script src="{base}/{_widget_js_path()}"\n'
        f'        data-agent="{token}"\n'
        f'        data-position="right"\n'
        f'        data-color="#6366f1"\n'
        f"        async></script>"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/agents/{agent_id}/tokens",
    status_code=status.HTTP_201_CREATED,
    summary="Create an embed token for an agent",
)
async def create_token(
    workspace_id: str,
    agent_id: str,
    payload: EmbedTokenCreate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)

        token_id = str(uuid.uuid4())
        token_string = secrets.token_hex(32)
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO agent_embed_tokens
               (id, agent_id, token, label, is_active, allowed_origins,
                request_count, created_at, last_used_at)
               VALUES (?, ?, ?, ?, 1, ?, 0, ?, NULL)""",
            (
                token_id,
                agent_id,
                token_string,
                payload.label,
                _serialize_origins(payload.allowed_origins),
                now,
            ),
        )
        await db.commit()

        async with db.execute(
            "SELECT * FROM agent_embed_tokens WHERE id = ?", (token_id,)
        ) as cur:
            row = await cur.fetchone()

    log.info(
        "Embed token created",
        token_id=token_id,
        agent_id=agent_id,
        owner_id=user["id"],
    )
    # Full token is returned ONLY here — it is never shown again unmasked.
    return _token_to_dict(dict(row), mask=False)


@router.get(
    "/{workspace_id}/agents/{agent_id}/tokens",
    summary="List embed tokens for an agent",
)
async def list_tokens(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)

        async with db.execute(
            "SELECT * FROM agent_embed_tokens WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        ) as cur:
            rows = await cur.fetchall()

    return [_token_to_dict(dict(r), mask=True) for r in rows]


@router.get(
    "/{workspace_id}/agents/{agent_id}/tokens/{token_id}",
    summary="Get a single embed token",
)
async def get_token(
    workspace_id: str,
    agent_id: str,
    token_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        row = await _get_owned_token(db, workspace_id, agent_id, token_id, user)
    return _token_to_dict(row, mask=True)


@router.put(
    "/{workspace_id}/agents/{agent_id}/tokens/{token_id}",
    summary="Update an embed token (partial)",
)
async def update_token(
    workspace_id: str,
    agent_id: str,
    token_id: str,
    payload: EmbedTokenUpdate,
    user: dict = Depends(get_current_user),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update.",
        )

    async with get_db() as db:
        await _get_owned_token(db, workspace_id, agent_id, token_id, user)

        row = dict(
            await (
                await db.execute(
                    "SELECT * FROM agent_embed_tokens WHERE id = ?", (token_id,)
                )
            ).fetchone()
        )

        if "allowed_origins" in updates:
            updates["allowed_origins"] = _serialize_origins(updates["allowed_origins"])

        assignments = ", ".join(f"{key} = ?" for key in updates)
        await db.execute(
            f"UPDATE agent_embed_tokens SET {assignments} WHERE id = ?",
            (*updates.values(), token_id),
        )
        await db.commit()

        async with db.execute(
            "SELECT * FROM agent_embed_tokens WHERE id = ?", (token_id,)
        ) as cur:
            row = await cur.fetchone()

    log.info("Embed token updated", token_id=token_id, fields=sorted(updates))
    return _token_to_dict(dict(row), mask=True)


@router.delete(
    "/{workspace_id}/agents/{agent_id}/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an embed token permanently",
)
async def delete_token(
    workspace_id: str,
    agent_id: str,
    token_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _get_owned_token(db, workspace_id, agent_id, token_id, user)
        await db.execute(
            "DELETE FROM agent_embed_tokens WHERE id = ?", (token_id,)
        )
        await db.commit()

    log.info("Embed token deleted", token_id=token_id, owner_id=user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspace_id}/agents/{agent_id}/tokens/{token_id}/snippet",
    summary="Get the HTML embed snippet for a token",
)
async def get_snippet(
    workspace_id: str,
    agent_id: str,
    token_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        row = await _get_owned_token(db, workspace_id, agent_id, token_id, user)

    # The dashboard already holds a JWT, so return the unmasked value here.
    # The list/get/update representations remain masked.
    return EmbedSnippet(
        snippet=_build_snippet(row["token"]),
        token=row["token"],
    )
