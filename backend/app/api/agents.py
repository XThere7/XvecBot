"""
api/agents.py
Agent CRUD and conversation history — thin routing layer.
All logic lives in services/agent_service.py and services/conversation_service.py.
Every route is scoped to the authenticated owner of the workspace.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..core.database import get_db
from ..core.logging import get_logger
from ..models.agent import AgentCreate, AgentUpdate
from ..services import agent_service, conversation_service
from .deps import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Agents"])


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
        conversation = await conversation_service.get_conversation(
            db, conversation_id
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
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
        await conversation_service.delete_conversation(db, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
