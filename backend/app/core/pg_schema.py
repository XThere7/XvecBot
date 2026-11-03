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
    status      TEXT NOT NULL DEFAULT 'processing',
    -- Where the uploaded bytes live (legacy direct uploads). Needed so a
    -- delete can remove the file instead of leaving it on the volume.
    file_path   TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    plan            TEXT NOT NULL DEFAULT 'free',
    trial_ends_at   TEXT,
    welcome_email_sent_at TEXT,
    password_changed_at TEXT
);

CREATE TABLE IF NOT EXISTS workspaces (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    system_prompt  TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
    owner_id       TEXT NOT NULL REFERENCES users(id),
    created_at     TEXT NOT NULL,
    plan           TEXT NOT NULL DEFAULT 'free',
    plan_started_at TEXT
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
    created_at    TEXT NOT NULL,
    object_key    TEXT,
    content_type  TEXT,
    etag          TEXT
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
    welcome_message TEXT,
    icon_url      TEXT
);
CREATE INDEX IF NOT EXISTS idx_agents_workspace ON agents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(workspace_id, is_active);

CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    agent_id     TEXT REFERENCES agents(id) ON DELETE CASCADE,
    title        TEXT,
    updated_at   TEXT NOT NULL DEFAULT '',
    -- Links a conversation to the workspace whose data it quotes, so the
    -- workspace teardown can delete the transcript as well.
    workspace_id TEXT
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
    doc_id       TEXT,
    agent_id     TEXT
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

CREATE TABLE IF NOT EXISTS developer_api_keys (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id),
    workspace_id   TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    key_hash       TEXT NOT NULL UNIQUE,
    key_prefix     TEXT NOT NULL,
    is_active      INTEGER NOT NULL DEFAULT 1,
    allowed_agents TEXT,
    request_count  INTEGER NOT NULL DEFAULT 0,
    last_used_at   TEXT,
    expires_at     TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dev_keys_workspace ON developer_api_keys(workspace_id);
CREATE INDEX IF NOT EXISTS idx_dev_keys_hash ON developer_api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_events (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_ws_kind_created
    ON usage_events(workspace_id, kind, created_at);

CREATE TABLE IF NOT EXISTS usage_monthly (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month         TEXT NOT NULL,
    chat_messages INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, month)
);
CREATE INDEX IF NOT EXISTS idx_usage_monthly_user_month
    ON usage_monthly(user_id, month);

CREATE TABLE IF NOT EXISTS website_sources (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    pages_discovered INTEGER NOT NULL DEFAULT 0,
    pages_indexed    INTEGER NOT NULL DEFAULT 0,
    last_synced_at   TEXT,
    next_sync_at     TEXT,
    refresh_policy   TEXT NOT NULL DEFAULT 'manual',
    error_message    TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_website_sources_workspace
    ON website_sources(workspace_id);
CREATE INDEX IF NOT EXISTS idx_website_sources_due
    ON website_sources(refresh_policy, next_sync_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_website_sources_workspace_url
    ON website_sources(workspace_id, url);

CREATE TABLE IF NOT EXISTS website_pages (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES website_sources(id) ON DELETE CASCADE,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    title           TEXT,
    content_hash    TEXT,
    status          TEXT NOT NULL DEFAULT 'discovered',
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    last_indexed_at TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_website_pages_source
    ON website_pages(source_id);
CREATE INDEX IF NOT EXISTS idx_website_pages_workspace
    ON website_pages(workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_website_pages_source_url
    ON website_pages(source_id, url);

CREATE TABLE IF NOT EXISTS website_sync_jobs (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES website_sources(id) ON DELETE CASCADE,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    triggered_by    TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'running',
    pages_crawled   INTEGER NOT NULL DEFAULT 0,
    pages_indexed   INTEGER NOT NULL DEFAULT 0,
    pages_unchanged INTEGER NOT NULL DEFAULT 0,
    pages_failed    INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_website_sync_jobs_source
    ON website_sync_jobs(source_id, started_at);
CREATE INDEX IF NOT EXISTS idx_website_sync_jobs_workspace
    ON website_sync_jobs(workspace_id);

CREATE TABLE IF NOT EXISTS social_media_sources (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    normalized_url  TEXT NOT NULL,
    platform        TEXT NOT NULL,
    provider_post_id TEXT,
    title           TEXT,
    author_name     TEXT,
    published_at    TEXT,
    thumbnail_url   TEXT,
    content_text    TEXT,
    content_hash    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    extraction_method TEXT,
    error_code      TEXT,
    error_message   TEXT,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    imported_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_social_media_agent
    ON social_media_sources(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_social_media_workspace
    ON social_media_sources(workspace_id);
CREATE INDEX IF NOT EXISTS idx_social_media_status
    ON social_media_sources(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_social_media_hash
    ON social_media_sources(agent_id, content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_social_media_agent_url
    ON social_media_sources(workspace_id, agent_id, normalized_url);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    used_at       TEXT,
    requested_ip  TEXT
);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash
    ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
    ON password_reset_tokens(user_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    actor_id    TEXT,
    actor_email TEXT,
    action      TEXT NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    summary     TEXT NOT NULL,
    ip          TEXT,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_id);

CREATE TABLE IF NOT EXISTS error_events (
    id             TEXT PRIMARY KEY,
    ts             TEXT NOT NULL,
    path           TEXT NOT NULL,
    status         INTEGER,
    exception_type TEXT,
    message        TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_events_ts ON error_events(ts);

CREATE TABLE IF NOT EXISTS plan_changes (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_plan  TEXT,
    to_plan    TEXT NOT NULL,
    reason     TEXT,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_changes_user ON plan_changes(user_id);

CREATE TABLE IF NOT EXISTS payments (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_tzs   INTEGER NOT NULL,
    method       TEXT NOT NULL,
    reference    TEXT,
    period_start TEXT,
    period_end   TEXT,
    recorded_by  TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);

CREATE TABLE IF NOT EXISTS platform_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_events_created ON usage_events(created_at);
"""

# Best-effort ANN index. Wrapped in try/except by the caller: older pgvector
# builds without HNSW support (or restricted Neon roles) must not fail boot.
PG_ANN_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw "
    "ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)"
)

# Idempotent additive columns (kept for parity with the SQLite ALTER path).
PG_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "plan": "TEXT NOT NULL DEFAULT 'free'",
        "trial_ends_at": "TEXT",
        "welcome_email_sent_at": "TEXT",
        "password_changed_at": "TEXT",
        "role": "TEXT NOT NULL DEFAULT 'user'",
        "permissions": "TEXT",
        "last_login_at": "TEXT",
        "suspended_at": "TEXT",
        "suspended_reason": "TEXT",
        "totp_secret": "TEXT",
        "totp_enabled": "INTEGER NOT NULL DEFAULT 0",
        "recovery_codes": "TEXT",
        "totp_failed_at": "TEXT",
        "totp_failed_count": "INTEGER NOT NULL DEFAULT 0",
    },
    "usage_events": {
        "user_id": "TEXT",
        "agent_id": "TEXT",
        "channel": "TEXT",
        "model": "TEXT",
        "status": "TEXT",
        "latency_ms": "INTEGER",
        "prompt_tokens": "INTEGER",
        "completion_tokens": "INTEGER",
        "error_code": "TEXT",
        "month": "TEXT",
    },
    "workspaces": {
        "plan": "TEXT NOT NULL DEFAULT 'free'",
        "plan_started_at": "TEXT",
    },
    "conversations": {
        "agent_id": "TEXT REFERENCES agents(id) ON DELETE CASCADE",
        "title": "TEXT",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        # Links a transcript to the workspace whose data it quotes, so the
        # workspace teardown can delete the transcript too.
        "workspace_id": "TEXT",
    },
    "agents": {"welcome_message": "TEXT", "icon_url": "TEXT"},
    "chunks": {"workspace_id": "TEXT", "doc_id": "TEXT", "agent_id": "TEXT"},
    "chunk_embeddings": {"workspace_id": "TEXT", "doc_id": "TEXT"},
    "workspace_documents": {
        "object_key": "TEXT",
        "content_type": "TEXT",
        "etag": "TEXT",
    },
    # Where the bytes of a legacy direct upload live, so deleting the
    # document can delete the file instead of leaving it on the volume.
    "documents": {"file_path": "TEXT"},
}

# Indexes that depend on a column added by PG_ADDITIVE_COLUMNS. They are
# created after the ALTERs, otherwise an existing table without the column
# would fail the whole boot.
PG_ADDITIVE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_conversations_workspace "
    "ON conversations(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_agent "
    "ON chunks(workspace_id, agent_id)",
)


# Append-only guard for the admin audit log on Postgres.
PG_AUDIT_LOG_GUARDS = (
    """
    CREATE OR REPLACE FUNCTION audit_log_no_write() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log is append-only';
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_no_write();
    """,
    """
    CREATE OR REPLACE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_no_write();
    """,
)
