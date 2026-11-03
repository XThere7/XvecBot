"""
api/admin
Master admin panel routers. All routes live under /admin and are protected by
the router-level require_admin_role dependency; individual routes add their
permission checks on top.
"""
from fastapi import APIRouter, Depends

from . import (
    admins,
    audit,
    conversations,
    keys,
    knowledge,
    my_account,
    overview,
    platform,
    subscriptions,
    system,
    usage,
    users,
    workspaces,
)
from .deps import require_admin_role
from ...core.config import settings

router = APIRouter(
    prefix=settings.admin_route_prefix.rstrip("/"),
    tags=["Admin"],
    dependencies=[Depends(require_admin_role)],
)

router.include_router(overview.router)
router.include_router(users.router)
router.include_router(workspaces.router)
router.include_router(knowledge.router)
router.include_router(conversations.router)
router.include_router(usage.router)
router.include_router(subscriptions.router)
router.include_router(keys.router)
router.include_router(system.router)
router.include_router(audit.router)
router.include_router(admins.router)
router.include_router(platform.router)
router.include_router(my_account.router)
