"""
api/health.py
Health and readiness check endpoints.
Used by Docker, load balancers, and monitoring systems.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["health"])

_START_TIME = time.time()


@router.get("/health", summary="Basic liveness check")
async def health():
    """Returns 200 if the server is running."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.time() - _START_TIME, 1),
    }


@router.get("/health/ready", summary="Readiness check including DB")
async def readiness():
    """
    Returns 200 only if the database is reachable.
    Use this as the Kubernetes readinessProbe or Docker HEALTHCHECK.
    """
    db_ok = False
    try:
        async with get_db() as db:
            async with db.execute("SELECT 1") as cur:
                await cur.fetchone()
        db_ok = True
    except Exception as exc:
        log.error("Readiness DB check failed", error=str(exc))

    status = "ready" if db_ok else "not_ready"
    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
