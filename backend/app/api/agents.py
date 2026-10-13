"""
api/agents.py
Agent CRUD and conversation history — thin routing layer.
All logic lives in services/agent_service.py and services/conversation_service.py.
Every route is scoped to the authenticated owner of the workspace.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..models.agent import AgentCreate, AgentUpdate
from ..services import agent_chat_service, agent_service, conversation_service
from .deps import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Agents"])

# ── Bot icon upload ───────────────────────────────────────────────────────────
# PNG/JPG/WebP/GIF only, 2 MB max. Magic bytes are checked so a renamed
# document cannot be stored (and later served) as an image.
ICON_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ICON_ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
ICON_MAX_BYTES = 2 * 1024 * 1024
ICON_MAGIC_PREFIXES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",        # JPEG
    b"GIF87a", b"GIF89a",  # GIF
    b"RIFF",               # WebP (RIFF....WEBP — checked loosely, ext+MIME gate the rest)
)


def _icons_root() -> Path:
    """Upload root for bot icons (same volume as workspace uploads)."""
    root = settings.workspace_upload_path / "icons"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _icon_path_for(icon_url: Optional[str]) -> Optional[Path]:
    """
    Map a stored icon_url (/static/icons/<agent_id>/<file>) back to disk,
    or None. Traversal-guarded: the resolved path must stay inside the root.
    """
    if not icon_url or not icon_url.startswith("/static/icons/"):
        return None
    rel = icon_url[len("/static/icons/"):].lstrip("/")
    candidate = (_icons_root() / rel).resolve()
    try:
        candidate.relative_to(_icons_root().resolve())
    except ValueError:
        return None
    return candidate


@router.post(
    "/{workspace_id}/agents",
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent in a workspace",
)
async def create_agent(
    workspace_id: str,
    payload: AgentCreate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        agent = await agent_service.create_agent(
            db=db,
            workspace_id=workspace_id,
            owner_id=user["id"],
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            model=payload.model,
            temperature=payload.temperature,
            language=payload.language,
            welcome_message=payload.welcome_message,
        )
    return agent


@router.get(
    "/{workspace_id}/agents",
    summary="List agents in a workspace",
)
async def list_agents(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        return await agent_service.get_agents_for_workspace(
            db, workspace_id, user["id"]
        )


@router.get(
    "/{workspace_id}/agents/{agent_id}",
    summary="Get a single agent",
)
async def get_agent(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        return await agent_service.get_agent(db, agent_id, user["id"])


@router.put(
    "/{workspace_id}/agents/{agent_id}",
    summary="Update an agent (partial)",
)
async def update_agent(
    workspace_id: str,
    agent_id: str,
    payload: AgentUpdate,
    user: dict = Depends(get_current_user),
):
    updates = payload.model_dump(exclude_unset=True)
    async with get_db() as db:
        return await agent_service.update_agent(
            db, agent_id, user["id"], **updates
        )


@router.delete(
    "/{workspace_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent and its conversations",
)
async def delete_agent(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await agent_service.delete_agent(db, agent_id, user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Conversations ─────────────────────────────────────────────────────────────


async def _require_owned_agent(
    db,
    workspace_id: str,
    agent_id: str,
    user: dict,
) -> dict:
    """
    Verify the agent exists, belongs to the workspace in the path, and that the
    workspace is owned by the user. Raises 404/403 via agent_service.
    """
    agent = await agent_service.get_agent(db, agent_id, user["id"])
    if agent["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found in this workspace",
        )
    return agent


async def _require_owned_conversation(
    db,
    agent_id: str,
    conversation_id: str,
) -> dict:
    """
    Multi-tenancy binding (Task 1 audit fix): a conversation id is only valid
    inside the agent it was created for. Without this check, any authenticated
    user holding their OWN agent id could read or delete ANY conversation in
    the database — including other users' — by guessing its UUID in the path.
    chat_with_agent() already enforced this (foreign id → 404); the GET and
    DELETE endpoints did not. Legacy agent_id-NULL rows are never exposed here.
    """
    conversation = await conversation_service.get_conversation(db, conversation_id)
    if conversation is None or conversation.get("agent_id") != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


@router.get(
    "/{workspace_id}/agents/{agent_id}/conversations",
    summary="List conversations for an agent",
)
async def list_conversations(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)
        return await conversation_service.get_conversations_for_agent(db, agent_id)


@router.get(
    "/{workspace_id}/agents/{agent_id}/conversations/{conversation_id}",
    summary="Get a conversation and its messages",
)
async def get_conversation(
    workspace_id: str,
    agent_id: str,
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)
        conversation = await _require_owned_conversation(
            db, agent_id, conversation_id
        )
        messages = await conversation_service.get_conversation_messages(
            db, conversation_id
        )
    return {"conversation": conversation, "messages": messages}


@router.delete(
    "/{workspace_id}/agents/{agent_id}/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and its messages",
)
async def delete_conversation(
    workspace_id: str,
    agent_id: str,
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)
        await _require_owned_conversation(db, agent_id, conversation_id)
        await conversation_service.delete_conversation(db, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Chat ──────────────────────────────────────────────────────────────────────


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


@router.post(
    "/{workspace_id}/agents/{agent_id}/chat",
    summary="Send a message to an agent",
)
async def chat(
    workspace_id: str,
    agent_id: str,
    payload: AgentChatRequest,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)
        try:
            return await agent_chat_service.chat_with_agent(
                agent_id=agent_id,
                conversation_id=payload.conversation_id,
                message=payload.message,
                db=db,
            )
        except HTTPException:
            raise
        except Exception as exc:
            log.error("Agent chat error", error=str(exc), agent_id=agent_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat failed. Check server logs.",
            )


@router.post(
    "/{workspace_id}/agents/{agent_id}/conversations/new",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new empty conversation for an agent",
)
async def new_conversation(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await _require_owned_agent(db, workspace_id, agent_id, user)
        return await conversation_service.create_conversation(db, agent_id)


# ── Bot icon ──────────────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/agents/{agent_id}/icon",
    summary="Upload a bot icon (avatar) for an agent",
)
async def upload_icon(
    workspace_id: str,
    agent_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Set the agent's chat-bubble icon. Ownership chain verified
    (agent → workspace → owner) before anything is written.
    """
    async with get_db() as db:
        agent = await _require_owned_agent(db, workspace_id, agent_id, user)

        original = Path(file.filename or "").name
        ext = Path(original).suffix.lower()
        if ext not in ICON_ALLOWED_EXTENSIONS or (
            file.content_type not in ICON_ALLOWED_MIME_TYPES
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PNG, JPG, WebP, and GIF images are allowed.",
            )

        content = await file.read()
        if len(content) > ICON_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image must be under 2 MB.",
            )
        if not content.startswith(ICON_MAGIC_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PNG, JPG, WebP, and GIF images are allowed.",
            )

        dest_dir = _icons_root() / agent_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{original}"
        save_path = dest_dir / filename
        save_path.write_bytes(content)
        icon_url = f"/static/icons/{agent_id}/{filename}"

        # Remove the previous icon so orphan files never accumulate.
        old_path = _icon_path_for(agent.get("icon_url"))
        if old_path is not None and old_path != save_path:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                pass

        try:
            await db.execute(
                "UPDATE agents SET icon_url = ?, updated_at = ? WHERE id = ?",
                (
                    icon_url,
                    datetime.now(timezone.utc).isoformat(),
                    agent_id,
                ),
            )
            await db.commit()
            updated = await agent_service.get_agent(db, agent_id, user["id"])
        except Exception:
            save_path.unlink(missing_ok=True)
            raise

    log.info("Agent icon uploaded", agent_id=agent_id, icon_url=icon_url)
    return updated


@router.delete(
    "/{workspace_id}/agents/{agent_id}/icon",
    summary="Remove the bot icon (falls back to the default bubble)",
)
async def delete_icon(
    workspace_id: str,
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    """Verify ownership, delete the file, NULL the column."""
    async with get_db() as db:
        agent = await _require_owned_agent(db, workspace_id, agent_id, user)

        old_path = _icon_path_for(agent.get("icon_url"))
        if old_path is not None:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                pass

        await db.execute(
            "UPDATE agents SET icon_url = NULL, updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), agent_id),
        )
        await db.commit()
        updated = await agent_service.get_agent(db, agent_id, user["id"])

    log.info("Agent icon removed", agent_id=agent_id)
    return updated
