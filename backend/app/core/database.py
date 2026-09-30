"""
core/database.py
Async SQLite connection pool via aiosqlite.
Bootstraps the full schema (documents, chunks, conversations, messages)
and loads the sqlite-vec extension for vector similarity search.
"""
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import sqlite_vec

from .config import settings
from .logging import get_logger

log = get_logger(__name__)

# Resolve DB path via settings.database_path (handles relative vs absolute + project root)
_DB_PATH = settings.database_path
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec into a raw sqlite3 connection."""
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    upload_date TEXT NOT NULL,
    total_pages INTEGER NOT NULL,
    file_size   INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'processing'
);
"""

CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page        INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page     ON chunks(document_id, page);
"""

CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content         TEXT NOT NULL,
    citations       TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
"""

# sqlite-vec virtual table — stores chunk embeddings
CREATE_EMBEDDINGS = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding float[{settings.embedding_dimension}]
);
"""

# Phase 2 — multi-tenant tables (schemas also documented in models/workspace.py)
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
"""

CREATE_WORKSPACES = """
CREATE TABLE IF NOT EXISTS workspaces (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    system_prompt  TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
    owner_id       TEXT NOT NULL REFERENCES users(id),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);
"""

CREATE_WORKSPACE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS workspace_documents (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'uploaded',
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_docs_ws ON workspace_documents(workspace_id);
"""

# Phase 3 — Agent Builder (schemas also documented in models/agent.py)
CREATE_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    system_prompt TEXT NOT NULL,
    model         TEXT NOT NULL,
    temperature   REAL NOT NULL DEFAULT 0.7,
    language      TEXT NOT NULL DEFAULT 'English',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    welcome_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_agents_workspace ON agents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(workspace_id, is_active);
"""

# Phase 4 — embeddable widget tokens
CREATE_AGENT_EMBED_TOKENS = """
CREATE TABLE IF NOT EXISTS agent_embed_tokens (
    id            TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    token         TEXT NOT NULL UNIQUE,
    label         TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    allowed_origins TEXT,
    request_count INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_embed_tokens_agent ON agent_embed_tokens(agent_id);
CREATE INDEX IF NOT EXISTS idx_embed_tokens_token  ON agent_embed_tokens(token);
"""

# `conversations` already exists from Phase 1 with a narrower schema, so
# CREATE TABLE IF NOT EXISTS against it is a silent no-op. The agent columns
# are appended instead — additive and data-preserving.
# `messages` gains no column: it reuses the existing `citations` JSON array.
# An agent conversation is any conversations row with a non-NULL agent_id.
AGENT_CONVERSATION_COLUMNS = {
    "agent_id": "TEXT REFERENCES agents(id) ON DELETE CASCADE",
    "title": "TEXT",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

# `agents` predates the Phase 4 widget, so the same CREATE TABLE IF NOT EXISTS
# is a no-op there too — the welcome_message column is appended instead.
AGENT_TABLE_COLUMNS = {
    "welcome_message": "TEXT",
}

# An earlier revision of this change added a duplicate `messages.sources`
# column. It is dropped so a single source field (citations) is maintained.
# Safe: the column was never written to.
DEPRECATED_COLUMNS = {
    "messages": ("sources",),
}


async def _add_columns_if_missing(
    db: aiosqlite.Connection,
    table: str,
    columns: dict,
) -> None:
    """
    Append any missing columns to an existing table.

    SQLite has no ALTER TABLE ... ADD COLUMN IF NOT EXISTS, so the existing
    columns are read from PRAGMA table_info first and only absent ones are
    added. Existing rows keep their data (SQLite backfills the default).
    """
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        existing = {row[1] for row in await cur.fetchall()}

    added = []
    for column, definition in columns.items():
        if column not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            added.append(column)

    if added:
        await db.commit()
        log.info("Schema extended", table=table, columns=sorted(added))


async def _drop_deprecated_columns(
    db: aiosqlite.Connection,
    table: str,
    columns: tuple,
) -> None:
    """Remove columns superseded by a later revision (no-op when absent)."""
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        existing = {row[1] for row in await cur.fetchall()}

    dropped = []
    for column in columns:
        if column in existing:
            await db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            dropped.append(column)

    if dropped:
        await db.commit()
        log.info("Deprecated columns removed", table=table, columns=sorted(dropped))


async def init_db() -> None:
    """Create all tables. Safe to call on every startup (IF NOT EXISTS)."""
    log.info("Initialising database", path=str(_DB_PATH))
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.enable_load_extension(True)
        await db.load_extension(sqlite_vec.loadable_path())
        await db.enable_load_extension(False)

        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(CREATE_DOCUMENTS)
        await db.executescript(CREATE_CHUNKS)
        await db.executescript(CREATE_CONVERSATIONS)
        await db.executescript(CREATE_MESSAGES)
        await db.executescript(CREATE_EMBEDDINGS)
        await db.executescript(CREATE_USERS)
        await db.executescript(CREATE_WORKSPACES)
        await db.executescript(CREATE_WORKSPACE_DOCUMENTS)
        await db.executescript(CREATE_AGENTS)
        await db.executescript(CREATE_AGENT_EMBED_TOKENS)
        # Agent columns on the pre-existing Phase 1 conversations table (idempotent).
        await _add_columns_if_missing(db, "conversations", AGENT_CONVERSATION_COLUMNS)
        # `agents` gains the Phase 4 widget welcome_message column (idempotent).
        await _add_columns_if_missing(db, "agents", AGENT_TABLE_COLUMNS)
        # messages reuses `citations` — clean up the superseded `sources` column.
        await _drop_deprecated_columns(db, "messages", DEPRECATED_COLUMNS["messages"])
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id)"
        )
        await db.commit()
    log.info("Database ready")


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields a database connection with
    sqlite-vec loaded and foreign keys enabled.

    Usage:
        async with get_db() as db:
            rows = await db.execute("SELECT ...")
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.enable_load_extension(True)
        await db.load_extension(sqlite_vec.loadable_path())
        await db.enable_load_extension(False)

        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON;")
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
