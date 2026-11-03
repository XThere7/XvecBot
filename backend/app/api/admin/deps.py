"""
api/admin/deps.py
Authorization for the admin panel.

Every /admin route goes through require_admin_role (via the router-level
dependency in __init__.py) and most additionally through require_permission.
Role and permissions are re-read from the database on every request by
get_current_user, so demoting or suspending an admin takes effect
immediately — nothing is trusted from the JWT payload.
"""
from __future__ import annotations

import json

from fastapi import Depends, HTTPException, status

from ..deps import get_current_user
from ...core.auth import verify_password
from ...core import totp

# Permission keys an admin can be granted. The superadmin holds all of them
# implicitly and can never be restricted.
ALL_PERMISSIONS = (
    "overview.read",
    "users.read",
    "users.manage",
    "workspaces.read",
    "workspaces.manage",
    "knowledge.read",
    "knowledge.manage",
    "conversations.read",
    "analytics.read",
    "billing.read",
    "billing.manage",
    "keys.manage",
    "system.read",
    "audit.read",
)

# Never grantable to an admin (superadmin-only surfaces).
SUPERADMIN_ONLY_PERMISSIONS = (
    "admins.manage",
    "platform.manage",
    "users.delete",
    "superadmin.manage",
)

PERMISSION_PRESETS = {
    "support": ["overview.read", "users.read", "users.manage",
                "workspaces.read", "knowledge.read", "keys.manage"],
    "operations": ["overview.read", "users.read", "workspaces.read",
                   "workspaces.manage", "knowledge.read", "knowledge.manage",
                   "system.read"],
    "finance": ["overview.read", "billing.read", "billing.manage", "audit.read"],
    "analyst": ["overview.read", "analytics.read", "audit.read", "system.read"],
}


def parsed_permissions(user: dict) -> list[str]:
    if user.get("role") == "superadmin":
        return list(ALL_PERMISSIONS)
    try:
        value = json.loads(user.get("permissions") or "[]")
        if isinstance(value, list):
            return [str(item) for item in value]
    except (ValueError, TypeError):
        pass
    return []


async def require_admin_role(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user


def require_permission(permission: str):
    async def dependency(user: dict = Depends(require_admin_role)) -> dict:
        if user.get("role") == "superadmin":
            return user
        if permission not in parsed_permissions(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to do that.",
            )
        return user

    return dependency


async def require_superadmin(user: dict = Depends(require_admin_role)) -> dict:
    if user.get("role") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required.",
        )
    return user


async def verify_reauth(
    user: dict, password: str | None, code: str | None
) -> bool:
    """Re-authentication before sensitive actions: password (+ TOTP if on)."""
    if not password or not verify_password(password, user.get("hashed_password", "")):
        return False
    if user.get("totp_enabled") and user.get("totp_secret"):
        secret = totp.decrypt_secret(user["totp_secret"])
        if not secret or not code or not totp.verify_code(secret, code):
            return False
    return True
