"""
Minimal in-process scheduler for scheduled website refreshes.

Runs inside the FastAPI event loop and checks every 10 minutes for sources
whose ``next_sync_at`` is due. No Redis/Celery/broker is involved. The
production compose stack runs a single uvicorn worker (the rate limiter is
already process-local), so one scheduler per API process is correct.

Limitation: running multiple API replicas would start one scheduler per
replica. In that case add an advisory lock before enabling scheduled syncs at
scale.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .logging import get_logger

log = get_logger(__name__)

SCHEDULER_INTERVAL_SECONDS = 600  # every 10 minutes

_running_tasks: set[asyncio.Task] = set()


async def _check_and_dispatch() -> None:
    from .database import get_db

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        async with db.execute(
            """SELECT id FROM website_sources
               WHERE refresh_policy IN ('weekly', 'daily')
                 AND next_sync_at IS NOT NULL
                 AND next_sync_at <= ?
                 AND status != 'syncing'
               ORDER BY next_sync_at ASC""",
            (now,),
        ) as cur:
            rows = await cur.fetchall()

    for row in rows:
        source_id = row["id"]
        task = asyncio.create_task(_sync_with_fresh_db(source_id))
        _running_tasks.add(task)
        task.add_done_callback(_running_tasks.discard)


async def _sync_with_fresh_db(source_id: str) -> None:
    from .database import get_db
    from ..services.website_training_service import sync_website_source

    try:
        async with get_db() as db:
            await sync_website_source(
                source_id,
                triggered_by="scheduled",
                db=db,
            )
    except Exception as exc:  # pragma: no cover - service already catches
        log.error("Scheduled website sync crashed", source_id=source_id, error=str(exc))


async def run_scheduler(app) -> None:
    """
    Background loop started by the FastAPI lifespan.

    Never crashes the process: every tick catches and logs its own errors.
    """
    log.info("Website refresh scheduler started", interval_seconds=SCHEDULER_INTERVAL_SECONDS)
    try:
        while True:
            await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
            try:
                await _check_and_dispatch()
            except Exception as exc:
                log.error("Website refresh scheduler tick failed", error=str(exc))
    except asyncio.CancelledError:
        log.info("Website refresh scheduler stopping")
        raise
    finally:
        for task in list(_running_tasks):
            task.cancel()
        if _running_tasks:
            await asyncio.gather(*_running_tasks, return_exceptions=True)
        _running_tasks.clear()
