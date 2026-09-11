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
