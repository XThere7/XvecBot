"""
core/pg_pool.py (Phase 0+1)
Shared asyncpg pool for the Postgres (Neon) path, with pgvector codec
registration so `embedding <=> $1` works with plain list[float] params.
"""
from __future__ import annotations

import asyncpg

from .config import settings
from .logging import get_logger

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None


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


async def get_pg_pool() -> asyncpg.Pool:
    """Process-wide pool singleton (min/max from settings)."""
    global _pool
    if _pool is None or _pool.is_closing():
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
    return _pool


async def close_pg_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
