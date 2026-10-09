"""
core/pg_compat.py (Phase 0+1)
Minimal asyncpg adapter that mimics the aiosqlite subset used across the
codebase, so the ~60 existing `db.execute("... ? ...", params)` call sites
run unchanged on Postgres.

Supported surface:
  - await db.execute(sql, params?) -> PgCursor
  - async with db.execute(sql, params?) as cur: ...
  - await db.executescript(sql)   (splits on ';', skips PRAGMA/vec0)
  - await db.commit() / await db.rollback()  (no-ops: asyncpg autocommit)
  - cur.fetchall() / cur.fetchone(), rows support row["col"] and row[0]
    (native asyncpg.Record already supports both)

Placeholder translation: each `?` becomes `$1..$n` in order.
SQLite-only statements (PRAGMA, vec0 DDL, MATCH) must be branched by the
caller — execute() raises RuntimeError for PRAGMA to surface missed branches.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

_QMARK = re.compile(r"\?")


def translate_qmarks(sql: str) -> str:
    """Replace each `?` placeholder with Postgres `$n` numbering."""
    idx = 0

    def _repl(_: re.Match) -> str:
        nonlocal idx
        idx += 1
        return f"${idx}"

    return _QMARK.sub(_repl, sql)


def _looks_like_sqlite_only(sql: str) -> str | None:
    s = sql.strip().upper()
    if s.startswith("PRAGMA"):
        return "PRAGMA is SQLite-only (branch this call for Postgres)"
    if "USING VEC0" in s:
        return "vec0 virtual table is SQLite-only (use pg chunk_embeddings table)"
    if " MATCH " in s and "CHUNK_EMBEDDINGS" in s:
        return "vec0 MATCH KNN is SQLite-only (use pgvector <=> branch)"
    return None


class PgCursor:
    """Wraps asyncpg rows with the aiosqlite cursor API used in the codebase."""

    def __init__(self, rows: list[Any]):
        self._rows = list(rows or [])
        self._consumed = False

    async def fetchall(self) -> list[Any]:
        return list(self._rows)

    async def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    async def __aenter__(self) -> "PgCursor":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _Executable:
    """Awaitable + async-CM returned by PgConn.execute (mirrors aiosqlite)."""

    def __init__(self, coro_factory):
        self._coro_factory = coro_factory
        self._cursor: PgCursor | None = None

    def __await__(self):
        async def _run():
            self._cursor = await self._coro_factory()
            return self._cursor

        return _run().__await__()

    async def __aenter__(self) -> PgCursor:
        self._cursor = await self._coro_factory()
        return self._cursor

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class PgConn:
    """Thin wrapper around an asyncpg.Connection with aiosqlite-style API."""

    def __init__(self, conn):
        self._conn = conn

    @property
    def raw(self):
        return self._conn

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> _Executable:
        problem = _looks_like_sqlite_only(sql)
        if problem:
            raise RuntimeError(f"Postgres path hit SQLite-only SQL: {problem}: {sql[:120]}")

        async def _run() -> PgCursor:
            pg_sql = translate_qmarks(sql)
            args = tuple(params or ())
            stripped = pg_sql.strip().upper()
            if stripped.startswith(("SELECT", "WITH", "TABLE", "EXPLAIN")):
                rows = await self._conn.fetch(pg_sql, *args)
                return PgCursor(rows)
            await self._conn.execute(pg_sql, *args)
            return PgCursor([])

        return _Executable(_run)

    async def executescript(self, sql: str) -> None:
        for stmt in (s.strip() for s in sql.split(";")):
            if not stmt:
                continue
            if stmt.upper().startswith("PRAGMA") or "USING VEC0" in stmt.upper():
                continue
            await self._conn.execute(stmt)

    async def commit(self) -> None:
        # asyncpg autocommits outside explicit transactions — nothing to do.
        return None

    async def rollback(self) -> None:
        return None
