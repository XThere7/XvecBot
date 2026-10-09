"""
core/pg_schema.py (Phase 0+1)
Postgres DDL baseline for Neon production. Mirrors the final SQLite schema
1:1 (TEXT/INTEGER/REAL, same table/column names) so the existing raw-SQL
call sites run unchanged via the pg_compat `?` -> `$n` adapter.

Deliberate deviations from SQLite (required):
  - CREATE TABLE order fixed so REFERENCES targets exist first.
  - chunks includes workspace_id/doc_id directly (added at runtime on SQLite).
  - conversations includes agent_id/title/updated_at directly.
  - agents includes welcome_message directly.
  - chunk_embeddings is a regular TABLE with a vector(384) column
    (replaces `CREATE VIRTUAL TABLE ... USING vec0`), plus workspace_id/doc_id
    so KNN filtering happens in-SQL instead of the Python over-fetch.
  - No PRAGMA / journal_mode / vec extension loading.

Timestamps stay TEXT (ISO strings, as the code writes them) and booleans stay
INTEGER (0/1) in this baseline to avoid coercion churn. A follow-up can move
them to TIMESTAMPTZ/BOOLEAN once pydantic models are updated.
"""
from __future__ import annotations

PG_PREABLE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"""

# Order matters for REFERENCES. IF NOT EXISTS everywhere (idempotent).
PG_TABLES = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    upload_date TEXT NOT NULL,
    total_pages INTEGER NOT NULL,
    file_size   INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'processing'
);

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    system_prompt  TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
    owner_id       TEXT NOT NULL REFERENCES users(id),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

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

CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    agent_id   TEXT REFERENCES agents(id) ON DELETE CASCADE,
    title      TEXT,
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content         TEXT NOT NULL,
    citations       TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page        INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    workspace_id TEXT,
    doc_id       TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page     ON chunks(document_id, page);
CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON chunks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id     TEXT PRIMARY KEY,
    workspace_id TEXT,
    doc_id       TEXT,
    embedding    vector(384)
);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_workspace ON chunk_embeddings(workspace_id);

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

# Best-effort ANN index. Wrapped in try/except by the caller: older pgvector
# builds without HNSW support (or restricted Neon roles) must not fail boot.
PG_ANN_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw "
    "ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)"
)

# Idempotent additive columns (kept for parity with the SQLite ALTER path).
PG_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "conversations": {
        "agent_id": "TEXT REFERENCES agents(id) ON DELETE CASCADE",
        "title": "TEXT",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    },
    "agents": {"welcome_message": "TEXT"},
    "chunks": {"workspace_id": "TEXT", "doc_id": "TEXT"},
    "chunk_embeddings": {"workspace_id": "TEXT", "doc_id": "TEXT"},
}
