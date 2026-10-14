"""
services/api_key_service.py (Phase 6 — BotBase developer platform).

Long-lived developer API keys: the plaintext key is shown exactly once at
creation and never stored — only its SHA-256 hash. Format sk-botbase-{40 hex}
(the sk-xvec- prefix from the original spec was renamed with the platform).
"""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import HTTPException, status

from ..core.logging import get_logger

log = get_logger(__name__)

KEY_PREFIX_LABEL = "sk-botbase-"
KEY_SUFFIX_HEX_CHARS = 40
KEY_DISPLAY_PREFIX_CHARS = 12
MAX_NAME_LENGTH = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_key, key_hash, key_prefix). The full key is shown to the
    user once and never stored — only key_hash goes in the DB.
    """
    full_key = KEY_PREFIX_LABEL + secrets.token_hex(KEY_SUFFIX_HEX_CHARS // 2)
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    key_prefix = full_key[:KEY_DISPLAY_PREFIX_CHARS]
    return full_key, key_hash, key_prefix


def _row_to_dict(row) -> dict:
    """Public shape — key_hash is NEVER included (see _require_no_hash)."""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "workspace_id": row["workspace_id"],
        "name": row["name"],
        "key_prefix": row["key_prefix"],
        "is_active": row["is_active"],
        "allowed_agents": json.loads(row["allowed_agents"])
        if row["allowed_agents"]
        else None,
        "request_count": row["request_count"],
        "last_used_at": row["last_used_at"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
    }


async def _require_owned_workspace(
    db: aiosqlite.Connection, workspace_id: str, owner_id: str
) -> None:
    """404 for missing AND foreign workspaces (platform convention, no 403)."""
    async with db.execute(
        "SELECT owner_id FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or row["owner_id"] != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )


async def create_api_key(
    db: aiosqlite.Connection,
    user_id: str,
    workspace_id: str,
    name: str,
    allowed_agents: Optional[list[str]] = None,
    expires_at: Optional[str] = None,
) -> tuple[dict, str]:
    """
    Validate ownership, generate + store the hashed key.
    Returns (record, full_plaintext_key) — the plaintext appears HERE ONLY.
    """
    await _require_owned_workspace(db, workspace_id, user_id)
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Key name is required.",
        )
    if len(clean_name) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Key name must be at most 100 characters.",
        )

    # allowed_agents referencing foreign agents is validated at CALL time
    # (403 workspace mismatch), so creation stays permissive here. Malformed
    # entries are rejected now to fail fast on typos.
    agents_json = None
    if allowed_agents is not None:
        if not isinstance(allowed_agents, list) or not all(
            isinstance(a, str) and a for a in allowed_agents
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="allowed_agents must be a list of agent ID strings.",
            )
        agents_json = json.dumps(sorted(set(allowed_agents)))

    if expires_at is not None:
        try:
            datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at must be an ISO datetime.",
            )

    full_key, key_hash, key_prefix = generate_api_key()
    key_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO developer_api_keys
           (id, user_id, workspace_id, name, key_hash, key_prefix,
            is_active, allowed_agents, request_count, created_at, expires_at,
            last_used_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, ?, ?, NULL)""",
        (
            key_id,
            user_id,
            workspace_id,
            clean_name,
            key_hash,
            key_prefix,
            agents_json,
            _now(),
            expires_at,
        ),
    )
    await db.commit()
    log.info("Developer API key created", key_id=key_id, workspace_id=workspace_id)

    async with db.execute(
        "SELECT * FROM developer_api_keys WHERE id = ?", (key_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row), full_key


async def verify_api_key(db: aiosqlite.Connection, raw_key: str) -> Optional[dict]:
    """
    Hash and look up. Returns the record iff found AND active AND unexpired,
    else None — reason never distinguished (no oracle for attackers).
    Bumps last_used_at / request_count fire-and-forget.
    """
    if not raw_key:
        return None
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    async with db.execute(
        "SELECT * FROM developer_api_keys WHERE key_hash = ?", (digest,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or not row["is_active"]:
        return None
    if row["expires_at"]:
        try:
            expires = datetime.fromisoformat(
                row["expires_at"].replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now >= expires:
                return None
        except ValueError:
            return None
    try:
        await db.execute(
            "UPDATE developer_api_keys SET last_used_at = ?, "
            "request_count = request_count + 1 WHERE id = ?",
            (_now(), row["id"]),
        )
        await db.commit()
    except Exception as exc:
        log.warning("API key usage update failed", error=str(exc))
    return _row_to_dict(row)


async def get_api_keys_for_workspace(
    db: aiosqlite.Connection, workspace_id: str, user_id: str
) -> list[dict]:
    """All keys in the workspace, prefix only — key_hash never leaves the DB."""
    await _require_owned_workspace(db, workspace_id, user_id)
    async with db.execute(
        "SELECT * FROM developer_api_keys WHERE workspace_id = ? "
        "ORDER BY created_at DESC",
        (workspace_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def _get_owned_key(
    db: aiosqlite.Connection, key_id: str, user_id: str
) -> dict:
    """Fetch by id and verify the key's workspace belongs to the user."""
    async with db.execute(
        "SELECT * FROM developer_api_keys WHERE id = ?", (key_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    await _require_owned_workspace(db, row["workspace_id"], user_id)
    return dict(row)


async def get_api_key(
    db: aiosqlite.Connection, key_id: str, user_id: str
) -> dict:
    """Single key (prefix only), ownership verified."""
    return _row_to_dict(await _get_owned_key(db, key_id, user_id))


async def update_api_key(
    db: aiosqlite.Connection,
    key_id: str,
    user_id: str,
    name: Optional[str] = None,
    allowed_agents: Optional[list[str] | None] = "__unset__",
    is_active: Optional[int] = None,
) -> dict:
    """Partial update. allowed_agents=null resets to all-agents access."""
    record = await _get_owned_key(db, key_id, user_id)
    updates: dict = {}
    if name is not None:
        clean = name.strip()
        if not clean or len(clean) > MAX_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Key name must be 1-100 characters.",
            )
        updates["name"] = clean
    if allowed_agents != "__unset__":
        if allowed_agents is not None and (
            not isinstance(allowed_agents, list)
            or not all(isinstance(a, str) and a for a in allowed_agents)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="allowed_agents must be a list of agent ID strings or null.",
            )
        updates["allowed_agents"] = (
            json.dumps(sorted(set(allowed_agents))) if allowed_agents else None
        )
    if is_active is not None:
        if is_active not in (0, 1, True, False):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="is_active must be 0 or 1.",
            )
        updates["is_active"] = 1 if is_active else 0
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE developer_api_keys SET {assignments} WHERE id = ?",
            (*updates.values(), key_id),
        )
        await db.commit()
    _ = record
    return _row_to_dict(await _get_owned_key(db, key_id, user_id))


async def revoke_api_key(
    db: aiosqlite.Connection, key_id: str, user_id: str
) -> dict:
    """Set is_active=0. Ownership verified. Returns the updated record."""
    return await update_api_key(db, key_id, user_id, is_active=0)


async def delete_api_key(db: aiosqlite.Connection, key_id: str, user_id: str) -> None:
    """Hard delete. Ownership verified."""
    await _get_owned_key(db, key_id, user_id)
    await db.execute("DELETE FROM developer_api_keys WHERE id = ?", (key_id,))
    await db.commit()
    log.info("Developer API key deleted", key_id=key_id)
