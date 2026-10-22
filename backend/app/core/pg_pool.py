"""
core/pg_pool.py (Phase 0+1)
Shared asyncpg pool for the Postgres (Neon) path, with pgvector codec
registration so `embedding <=> $1` works with plain list[float] params.
"""
from __future__ import annotations

import asyncio

import asyncpg

from .config import settings
from .logging import get_logger

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None
# The event loop the pool was created on. asyncpg connections are bound to
# the loop that created them, so a pool must never outlive its loop.
_pool_loop: asyncio.AbstractEventLoop | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    try:
        from pgvector.asyncpg import register_vector

        await register_vector(conn)
    except Exception as exc:  # extension may not exist yet on first boot — retried later
        log.warning("pgvector codec registration skipped", error=str(exc))


async def ensure_vector_codec(conn: asyncpg.Connection) -> None:
    """(Re-)register the pgvector codec on a live connection (idempotent)."""
    if getattr(conn, "_xvec_vector_codec", False):
        return
    from pgvector.asyncpg import register_vector

    await register_vector(conn)
    try:
        conn._xvec_vector_codec = True  # type: ignore[attr-defined]
    except Exception:
        pass


async def _ensure_pg_extensions() -> None:
    """
    Create the extensions the app relies on BEFORE the pool opens.

    `register_vector()` inspects the server's type catalog when a connection
    is opened. On a brand-new database (the compose stack's first boot) the
    `vector` extension has not been created yet, so every pooled connection
    would silently miss the codec and vector parameters could fail. Creating
    the extensions first makes the first boot behave exactly like every
    later one.

    Best-effort: a role without DDL rights (some managed providers) logs a
    warning; the schema init repeats the same idempotent statements.
    """
    try:
        conn = await asyncpg.connect(settings.asyncpg_dsn)
    except Exception as exc:
        log.warning("Could not open a pre-flight Postgres connection", error=str(exc))
        return
    try:
        for ddl in (
            "CREATE EXTENSION IF NOT EXISTS vector",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        ):
            try:
                await conn.execute(ddl)
            except Exception as exc:  # missing privilege, or extension absent
                log.warning("Postgres extension unavailable", ddl=ddl, error=str(exc))
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_pg_pool() -> asyncpg.Pool:
    """Process-wide pool singleton (min/max from settings)."""
    global _pool, _pool_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - no running loop, no caller
        loop = None
    if _pool is not None and not _pool.is_closing():
        if loop is None or _pool_loop is loop:
            return _pool
        # The pool belongs to a different event loop (tests, a lifespan
        # restart). asyncpg connections are bound to the loop that created
        # them, so retire this pool and build a fresh one for this loop.
        log.warning("Rebuilding Postgres pool for a new event loop")
        try:
            await _pool.close()
        except Exception as exc:
            log.debug("Old Postgres pool close failed", error=str(exc))
        _pool = None
    await _ensure_pg_extensions()
    log.info(
        "Opening Postgres pool",
        max_size=settings.pg_pool_max_size,
    )
    _pool = await asyncpg.create_pool(
        settings.asyncpg_dsn,
        min_size=settings.pg_pool_min_size,
        max_size=settings.pg_pool_max_size,
        init=_init_conn,
    )
    _pool_loop = loop
    return _pool


async def close_pg_pool() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:
            log.warning("Postgres pool close failed", error=str(exc))
        _pool = None
        _pool_loop = None
