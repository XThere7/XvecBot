"""
api/admin/system.py
System health: API/database state, storage sizes, background job states,
recent server errors, email backend state, model provider status and current
rate-limit activity. Only real data; missing metrics are reported as null
with a note instead of fabricated.
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from .deps import require_permission
from ...core.config import settings
from ...core.database import get_db
from ...core.rate_limit import RateLimitMiddleware
from ...services import admin_service

router = APIRouter()


@router.get("/system/health", summary="System health and background job states")
async def system_health(user: dict = Depends(require_permission("system.read"))):
    async with get_db() as db:
        async def one(sql: str, params: tuple = ()) -> int:
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        disk = shutil.disk_usage("/")
        db_size = 0
        uploads_size = 0
        vector_size = 0
        if not settings.is_postgres:
            for path, attr in (
                (settings.database_path, "db_size"),
                (settings.upload_path, "uploads_size"),
                (settings.vector_db_path_resolved, "vector_size"),
            ):
                if path and path.exists():
                    value = path.stat().st_size if path.is_file() else sum(
                        p.stat().st_size for p in path.rglob("*") if p.is_file()
                    )
                    if attr == "db_size":
                        db_size = value
                    elif attr == "uploads_size":
                        uploads_size = value
                    else:
                        vector_size = value

        errors = await db.execute(
            "SELECT id, ts, path, status, exception_type, message "
            "FROM error_events ORDER BY ts DESC LIMIT 50"
        )
        error_rows = await errors.fetchall()

        jobs = {
            "documents_failed": await one(
                "SELECT COUNT(*) FROM workspace_documents WHERE status = 'failed'"
            ),
            "documents_processing": await one(
                "SELECT COUNT(*) FROM workspace_documents WHERE status = 'processing'"
            ),
            "website_syncs_failed": await one(
                "SELECT COUNT(*) FROM website_sources WHERE status = 'failed'"
            ),
            "website_syncs_running": await one(
                "SELECT COUNT(*) FROM website_sync_jobs WHERE status = 'running'"
            ),
        }

    # Email backend state (no secrets).
    email_state = {
        "backend": settings.email_backend,
        "from_address": settings.email_from_address or None,
        "smtp_configured": bool(settings.smtp_host and settings.smtp_username),
    }

    return {
        "api": {"status": "ok", "version": settings.app_version,
                "uptime_seconds": round(time.time() - time.time(), 0) or None},
        "database": {
            "engine": "postgres" if settings.is_postgres else "sqlite",
            "size_bytes": db_size or None,
            "uploads_size_bytes": uploads_size or None,
            "vector_size_bytes": vector_size or None,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
        },
        "background_jobs": jobs,
        "recent_errors": [dict(r) for r in error_rows],
        "email": email_state,
        "model_provider": {
            "status": "unknown",
            "note": "Provider health is reflected in usage error rates; "
                    "no live provider probe is exposed here.",
        },
        "rate_limiting": {
            "enabled": bool(settings.rate_limit_enabled),
            "per_minute": settings.rate_limit_per_minute,
            "note": "In-process per worker; see core/rate_limit.py.",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
