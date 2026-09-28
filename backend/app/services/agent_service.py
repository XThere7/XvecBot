"""
services/agent_service.py
Business logic for agent CRUD within a workspace.

The API layer calls this service and stays thin — no business logic in endpoints.
Every function verifies workspace ownership before touching an agent, so an agent
can only be read or modified by the owner of the workspace it belongs to.
"""
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import HTTPException, status

from ..core.agent_config import validate_agent_config
from ..core.logging import get_logger

log = get_logger(__name__)

# Columns a client is allowed to set on update (guards against arbitrary SQL).
_UPDATABLE_COLUMNS = (
    "name",
    "description",
    "system_prompt",
    "model",
    "temperature",
    "language",
    "is_active",
)


async def _require_owned_workspace(
    db: aiosqlite.Connection,
    workspace_id: str,
    owner_id: str,
) -> dict:
    """
    Return the workspace as a dict, or raise:
      404 if it does not exist, 403 if it belongs to someone else.
    """
    async with db.execute(
        "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    if row["owner_id"] != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this workspace",
        )
    return dict(row)


async def _get_agent_row(db: aiosqlite.Connection, agent_id: str) -> dict:
    """Fetch an agent row as a dict, or raise 404."""
    async with db.execute(
        "SELECT * FROM agents WHERE id = ?", (agent_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return dict(row)


async def create_agent(
    db: aiosqlite.Connection,
    workspace_id: str,
    owner_id: str,
    name: str,
    description: str | None,
    system_prompt: str,
    model: str,
    temperature: float,
    language: str,
) -> dict:
    """
    Create an agent inside a workspace.

    Raises 404 if the workspace is missing, 403 if it is not owned by owner_id.
    Returns the full agent dict.
    """
    await _require_owned_workspace(db, workspace_id, owner_id)

    # Validate and normalise the configuration before storing it.
    try:
        config = validate_agent_config(
            name=name,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO agents
           (id, workspace_id, name, description, system_prompt, model,
            temperature, language, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            agent_id,
            workspace_id,
            config["name"],
            description,
            config["system_prompt"],
            config["model"],
            config["temperature"],
            config["language"],
            now,
            now,
        ),
    )
    await db.commit()

    agent = await _get_agent_row(db, agent_id)
    log.info(
        "Agent created",
        agent_id=agent_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        name=config["name"],
    )
    return agent


async def get_agents_for_workspace(
    db: aiosqlite.Connection,
    workspace_id: str,
    owner_id: str,
) -> list[dict]:
    """Return every agent in the workspace, newest first. Ownership verified."""
    await _require_owned_workspace(db, workspace_id, owner_id)

    async with db.execute(
        "SELECT * FROM agents WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_agent(
    db: aiosqlite.Connection,
    agent_id: str,
    owner_id: str,
) -> dict:
    """
    Return a single agent.

    Raises 404 if the agent is missing, 403 if its workspace is not owned.
    """
    agent = await _get_agent_row(db, agent_id)
    await _require_owned_workspace(db, agent["workspace_id"], owner_id)
    return agent


async def update_agent(
    db: aiosqlite.Connection,
    agent_id: str,
    owner_id: str,
    **fields,
) -> dict:
    """
    Partially update an agent — only fields explicitly provided are changed,
    and `updated_at` is always refreshed.

    Raises 404 if the agent is missing, 403 if its workspace is not owned.
    Returns the updated agent dict.
    """
    agent = await _get_agent_row(db, agent_id)
    await _require_owned_workspace(db, agent["workspace_id"], owner_id)

    updates = {
        key: value
        for key, value in fields.items()
        if key in _UPDATABLE_COLUMNS and value is not None
    }

    # Validate the resulting configuration (merged with current values) so the
    # stored agent is always valid. Soft violations fall back to defaults.
    merged = {
        "name": updates.get("name", agent["name"]),
        "system_prompt": updates.get("system_prompt", agent["system_prompt"]),
        "model": updates.get("model", agent["model"]),
        "temperature": updates.get("temperature", agent["temperature"]),
        "language": updates.get("language", agent["language"]),
    }
    try:
        config = validate_agent_config(**merged)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Write back soft-validated values (clamped temperature, defaulted
    # model/language) so the stored row matches what was validated.
    for key in updates:
        updates[key] = config[key]

    now = datetime.now(timezone.utc).isoformat()
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        await db.execute(
            f"UPDATE agents SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), now, agent_id),
        )
    else:
        # Nothing to change — still bump updated_at so the caller sees activity.
        await db.execute(
            "UPDATE agents SET updated_at = ? WHERE id = ?",
            (now, agent_id),
        )
    await db.commit()

    updated = await _get_agent_row(db, agent_id)
    log.info(
        "Agent updated",
        agent_id=agent_id,
        owner_id=owner_id,
        fields=sorted(updates),
    )
    return updated


async def delete_agent(
    db: aiosqlite.Connection,
    agent_id: str,
    owner_id: str,
) -> None:
    """
    Delete an agent and everything hanging off it:
    its conversations' messages, then the conversations, then the agent row.

    Raises 404 if the agent is missing, 403 if its workspace is not owned.
    """
    agent = await _get_agent_row(db, agent_id)
    await _require_owned_workspace(db, agent["workspace_id"], owner_id)

    # Messages of every conversation belonging to this agent.
    await db.execute(
        """DELETE FROM messages
           WHERE conversation_id IN (
               SELECT id FROM conversations WHERE agent_id = ?
           )""",
        (agent_id,),
    )
    # Conversations of this agent.
    await db.execute(
        "DELETE FROM conversations WHERE agent_id = ?", (agent_id,)
    )
    # The agent itself.
    await db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    await db.commit()

    log.info("Agent deleted", agent_id=agent_id, owner_id=owner_id)
