"""
core/database.py
Dual-driver database bootstrap (Phase 0+1):
  - SQLite (default, local dev/tests): aiosqlite + sqlite-vec, as before.
  - Postgres (Neon production): asyncpg pool via core.pg_pool + DDL from
    core.pg_schema, with the aiosqlite-compatible wrapper in core.pg_compat
    so existing `db.execute("... ? ...")` call sites run unchanged.

Routing key is settings.is_postgres (DATABASE_URL scheme). The SQLite path
is byte-for-byte the previous behaviour.
"""
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Union

import aiosqlite
import sqlite_vec

from .config import settings
from .logging import get_logger
from ..models.email_agent import EMAIL_AGENT_TABLES_SQL
from ..models.engagement import ENGAGEMENT_TABLES_SQL

log = get_logger(__name__)


def _is_pg() -> bool:
    try:
        return bool(settings.is_postgres)
    except Exception:
        return False


# Resolve DB path via settings.database_path (handles relative vs absolute + project root)
# Postgres has no local file — keep None so import never mkdir()s a URL-shaped path.
_DB_PATH: Path | None = None
if not _is_pg():
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
    status      TEXT NOT NULL DEFAULT 'processing',
    file_path   TEXT
);
"""

CREATE_CHUNKS = """
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
    created_at      TEXT NOT NULL,
    plan            TEXT NOT NULL DEFAULT 'free',
    trial_ends_at   TEXT,
    welcome_email_sent_at TEXT,
    password_changed_at TEXT
);
"""

CREATE_WORKSPACES = """
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
    created_at    TEXT NOT NULL,
    object_key    TEXT,
    content_type  TEXT,
    etag          TEXT
);
CREATE INDEX IF NOT EXISTS idx_workspace_docs_ws ON workspace_documents(workspace_id);
"""

# Phase 2 — object-storage columns on pre-existing workspace_documents tables.
WORKSPACE_DOC_OBJECT_COLUMNS = {
    "object_key": "TEXT",
    "content_type": "TEXT",
    "etag": "TEXT",
}

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
    welcome_message TEXT,
    icon_url      TEXT
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

# Phase 6 — developer API keys (BotBase developer platform). Plaintext keys
# are never stored — only the SHA-256 hash. Brand prefix is sk-botbase-.
CREATE_DEVELOPER_API_KEYS = """
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
"""

# Website-to-Knowledge (Phase 7) — a crawled website is a knowledge source;
# every page becomes a virtual document indexed through the normal pipeline.
CREATE_WEBSITE_SOURCES = """
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
"""

CREATE_WEBSITE_PAGES = """
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
"""

CREATE_WEBSITE_SYNC_JOBS = """
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
"""

# Agent-scoped social media knowledge. A public post URL is a source, and the
# post text is indexed as a virtual document tagged with `chunks.agent_id`.
# Sources are owned by both the workspace and the agent so the same workspace
# can have different knowledge in different agents.
CREATE_SOCIAL_MEDIA_SOURCES = """
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
"""

# Additive column for pre-existing `chunks` tables. Social media imports are
# the only chunks with a non-NULL agent_id; NULL means workspace-wide knowledge
# shared by every agent.
CHUNK_SCOPE_COLUMNS = {
    "agent_id": "TEXT",
}

# Subscription metering — one immutable row per AI response. Keeping a ledger
# (rather than counting messages) means deleting a conversation does not hand
# the customer back paid quota, and a future billing provider can audit usage.
CREATE_USAGE_EVENTS = """
CREATE TABLE IF NOT EXISTS usage_events (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_ws_kind_created
    ON usage_events(workspace_id, kind, created_at);
"""

# Monthly account-level chat allowance. One row per user/month; the counter is
# incremented before every chat turn, including visitor messages on the widget.
CREATE_USAGE_MONTHLY = """
CREATE TABLE IF NOT EXISTS usage_monthly (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month         TEXT NOT NULL,
    chat_messages INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, month)
);
CREATE INDEX IF NOT EXISTS idx_usage_monthly_user_month
    ON usage_monthly(user_id, month);
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
    # Links a conversation to the workspace that owns the data it quotes.
    # Agent chats, workspace chats and single-tenant legacy queries set it,
    # so deleting a workspace can also delete the transcripts it produced.
    "workspace_id": "TEXT",
}

# `documents` predates the workspace documents table. Legacy uploads keep
# their bytes on the upload volume, so the row has to remember the path —
# otherwise deleting the document leaves the file behind forever.
LEGACY_DOCUMENT_COLUMNS = {
    "file_path": "TEXT",
}

# Subscription columns on pre-existing workspaces. Existing rows become Free
# (the column default) and keep all of their data.
WORKSPACE_PLAN_COLUMNS = {
    "plan": "TEXT NOT NULL DEFAULT 'free'",
    "plan_started_at": "TEXT",
}

# Account-level plan and trial state. Existing users keep their data and become
# Free; only new registrations receive a trial_ends_at timestamp.
USER_PLAN_COLUMNS = {
    "plan": "TEXT NOT NULL DEFAULT 'free'",
    "trial_ends_at": "TEXT",
}

# Exactly-once welcome email marker. Existing rows stay NULL and are never
# backfilled — only new registrations may set it, after a successful send.
USER_WELCOME_EMAIL_COLUMNS = {
    "welcome_email_sent_at": "TEXT",
}

# Session invalidation after a password reset. Existing rows stay NULL (their
# JWTs carry no `iat` and remain valid), so deploying this never logs out a
# user who has not reset their password.
USER_PASSWORD_CHANGED_COLUMNS = {
    "password_changed_at": "TEXT",
}

# Admin panel account state. `role` is user|admin|superadmin and can never be
# set through registration. `permissions` is a JSON array for admins.
# Suspension is checked on every authenticated + public + developer request.
USER_ADMIN_COLUMNS = {
    "role": "TEXT NOT NULL DEFAULT 'user'",
    "permissions": "TEXT",          # JSON array of permission keys (admins)
    "last_login_at": "TEXT",
    "suspended_at": "TEXT",
    "suspended_reason": "TEXT",
    "totp_secret": "TEXT",          # Fernet-encrypted TOTP seed
    "totp_enabled": "INTEGER NOT NULL DEFAULT 0",
    "recovery_codes": "TEXT",       # JSON array of SHA-256 hashes
    "totp_failed_at": "TEXT",
    "totp_failed_count": "INTEGER NOT NULL DEFAULT 0",
}

# Append-only admin audit log. SQLite triggers block UPDATE/DELETE; the
# Postgres schema installs the same guard. No API may edit or delete rows.
CREATE_AUDIT_LOG = """
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
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
"""

AUDIT_LOG_GUARDS = (
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit_log is append-only');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit_log is append-only');
    END;
    """,
)

# Per-request usage detail for the admin charts. Written fire-and-forget so
# chat latency is unaffected. `month` enables cheap retention purges.
USAGE_EVENT_DETAIL_COLUMNS = {
    "user_id": "TEXT",
    "agent_id": "TEXT",
    "channel": "TEXT",            # dashboard | widget | hosted | api
    "model": "TEXT",
    "status": "TEXT",             # ok | error | rate_limited
    "latency_ms": "INTEGER",
    "prompt_tokens": "INTEGER",
    "completion_tokens": "INTEGER",
    "error_code": "TEXT",
    "month": "TEXT",
}

# Unhandled server errors, captured by the exception middleware. No request
# bodies, no personal data, no secrets — path, status, class, truncated msg.
CREATE_ERROR_EVENTS = """
CREATE TABLE IF NOT EXISTS error_events (
    id             TEXT PRIMARY KEY,
    ts             TEXT NOT NULL,
    path           TEXT NOT NULL,
    status         INTEGER,
    exception_type TEXT,
    message        TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_events_ts ON error_events(ts);
"""

# History of every plan or trial change made through the admin panel.
CREATE_PLAN_CHANGES = """
CREATE TABLE IF NOT EXISTS plan_changes (
    id        TEXT PRIMARY KEY,
    user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_plan TEXT,
    to_plan   TEXT NOT NULL,
    reason    TEXT,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_changes_user ON plan_changes(user_id);
"""

# Manual payment ledger (no payment gateway yet).
CREATE_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_tzs    INTEGER NOT NULL,
    method        TEXT NOT NULL,  -- mpesa | tigo | airtel | bank | cash | other
    reference     TEXT,
    period_start  TEXT,
    period_end    TEXT,
    recorded_by   TEXT NOT NULL,
    recorded_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_recorded ON payments(recorded_at);
"""

# Key-value platform controls (signups, maintenance, emergency switch).
CREATE_PLATFORM_SETTINGS = """
CREATE TABLE IF NOT EXISTS platform_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT,
    updated_by TEXT
);
"""

# Single-use password reset links. Only the SHA-256 of the token is stored;
# the raw token exists solely in the emailed link. `used_at` doubles as the
# "superseded by a newer request" marker, so a fresh request atomically
# invalidates any earlier unused links.
CREATE_PASSWORD_RESET_TOKENS = """
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
"""

# `agents` predates the Phase 4 widget, so the same CREATE TABLE IF NOT EXISTS
# is a no-op there too — the welcome_message column is appended instead.
# icon_url (bot avatar, Phase 5-hardening) follows the same additive path.
AGENT_TABLE_COLUMNS = {
    "welcome_message": "TEXT",
    "icon_url": "TEXT",
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


async def _init_db_postgres() -> None:
    """Create all Postgres tables (Neon). Idempotent — safe every startup."""
    from .pg_pool import get_pg_pool
    from .pg_schema import PG_ANN_INDEX, PG_PREABLE, PG_TABLES

    log.info("Initialising Postgres database")
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute(PG_PREABLE)
        for stmt in (s.strip() for s in PG_TABLES.split(";")):
            if stmt:
                await conn.execute(stmt)
        # Engagement + Email Agent tables (shared DDL with SQLite).
        from ..models.email_agent import EMAIL_AGENT_TABLES_SQL
        from ..models.engagement import ENGAGEMENT_TABLES_SQL

        for block in (ENGAGEMENT_TABLES_SQL, EMAIL_AGENT_TABLES_SQL):
            for stmt in (s.strip() for s in block.split(";")):
                if stmt:
                    await conn.execute(stmt)
        # Additive columns for pre-existing tables (idempotent).
        from .pg_schema import PG_ADDITIVE_COLUMNS

        for table, columns in PG_ADDITIVE_COLUMNS.items():
            for column, definition in columns.items():
                await conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    f"{column} {definition}"
                )
        # Indexes over the additive columns (created after the ALTERs).
        from .pg_schema import PG_ADDITIVE_INDEXES

        for stmt in PG_ADDITIVE_INDEXES:
            await conn.execute(stmt)
        # Drop the superseded messages.sources column (no-op when absent).
        await conn.execute("ALTER TABLE messages DROP COLUMN IF EXISTS sources")
        # Append-only guard on the audit log.
        from .pg_schema import PG_AUDIT_LOG_GUARDS

        for stmt in PG_AUDIT_LOG_GUARDS:
            try:
                await conn.execute(stmt)
            except Exception as exc:
                log.warning("audit_log guard skipped", error=str(exc))
        # Best-effort ANN index — must never fail boot.
        try:
            await conn.execute(PG_ANN_INDEX)
        except Exception as exc:
            log.warning("pgvector ANN index skipped", error=str(exc))
    # Dispose the boot pool: its connections registered the vector codec
    # before CREATE EXTENSION ran. Fresh pools get a working codec.
    from .pg_pool import close_pg_pool as _close_pg_pool

    await _close_pg_pool()
    log.info("Postgres database ready")


async def init_db() -> None:
    """Create all tables. Safe to call on every startup (IF NOT EXISTS)."""
    if _is_pg():
        await _init_db_postgres()
        return
    assert _DB_PATH is not None, "SQLite path expected non-Postgres DATABASE_URL"
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
        await db.executescript(CREATE_USAGE_EVENTS)
        await db.executescript(CREATE_USAGE_MONTHLY)
        await db.executescript(CREATE_WORKSPACE_DOCUMENTS)
        await db.executescript(CREATE_AGENTS)
        await db.executescript(CREATE_AGENT_EMBED_TOKENS)
        await db.executescript(CREATE_DEVELOPER_API_KEYS)
        await db.executescript(CREATE_PASSWORD_RESET_TOKENS)
        await db.executescript(CREATE_AUDIT_LOG)
        await db.executescript(CREATE_ERROR_EVENTS)
        await db.executescript(CREATE_PLAN_CHANGES)
        await db.executescript(CREATE_PAYMENTS)
        await db.executescript(CREATE_PLATFORM_SETTINGS)
        # Append-only guards on the audit log (idempotent).
        for trigger in AUDIT_LOG_GUARDS:
            await db.executescript(trigger)
        await db.executescript(CREATE_WEBSITE_SOURCES)
        await db.executescript(CREATE_WEBSITE_PAGES)
        await db.executescript(CREATE_WEBSITE_SYNC_JOBS)
        await db.executescript(CREATE_SOCIAL_MEDIA_SOURCES)
        # Agent Actions, leads, collections, forms, support escalations.
        await db.executescript(ENGAGEMENT_TABLES_SQL)
        # Email Agent integrations, incoming mail, drafts, approvals, SMS.
        await db.executescript(EMAIL_AGENT_TABLES_SQL)
        # Agent-scoped knowledge marker for pre-existing chunks tables.
        await _add_columns_if_missing(db, "chunks", CHUNK_SCOPE_COLUMNS)
        # Agent columns on the pre-existing Phase 1 conversations table (idempotent).
        await _add_columns_if_missing(db, "conversations", AGENT_CONVERSATION_COLUMNS)
        await _add_columns_if_missing(db, "documents", LEGACY_DOCUMENT_COLUMNS)
        # `agents` gains the Phase 4 widget welcome_message column (idempotent).
        await _add_columns_if_missing(db, "agents", AGENT_TABLE_COLUMNS)
        # Account-level plan and 21-day trial state (idempotent).
        await _add_columns_if_missing(db, "users", USER_PLAN_COLUMNS)
        # Exactly-once welcome email marker (idempotent).
        await _add_columns_if_missing(db, "users", USER_WELCOME_EMAIL_COLUMNS)
        # Session invalidation timestamp after a password reset (idempotent).
        await _add_columns_if_missing(db, "users", USER_PASSWORD_CHANGED_COLUMNS)
        # Admin roles, permissions, suspension and TOTP state (idempotent).
        await _add_columns_if_missing(db, "users", USER_ADMIN_COLUMNS)
        # Per-request usage detail columns (idempotent).
        await _add_columns_if_missing(db, "usage_events", USAGE_EVENT_DETAIL_COLUMNS)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_created "
            "ON usage_events(created_at)"
        )
        # Subscription plan fields on pre-existing workspaces (idempotent).
        await _add_columns_if_missing(db, "workspaces", WORKSPACE_PLAN_COLUMNS)
        # Phase 2 object-storage columns on pre-existing workspace_documents.
        await _add_columns_if_missing(
            db, "workspace_documents", WORKSPACE_DOC_OBJECT_COLUMNS
        )
        # messages reuses `citations` — clean up the superseded `sources` column.
        await _drop_deprecated_columns(db, "messages", DEPRECATED_COLUMNS["messages"])
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_agent ON chunks(workspace_id, agent_id)"
        )
        await db.commit()
    log.info("Database ready")


@asynccontextmanager
async def get_db() -> AsyncGenerator[Union[aiosqlite.Connection, object], None]:
    """
    Async context manager yielding a database connection.

    SQLite (default): aiosqlite connection with sqlite-vec loaded, as before.
    Postgres (Neon): PgConn wrapper (core.pg_compat) with the same
        execute/commit/rollback surface and `?` placeholders translated.

    Usage:
        async with get_db() as db:
            rows = await db.execute("SELECT ...")
    """
    if _is_pg():
        from .pg_compat import PgConn
        from .pg_pool import get_pg_pool

        pool = await get_pg_pool()
        conn = await pool.acquire()
        try:
            yield PgConn(conn)
        except Exception:
            raise
        finally:
            await pool.release(conn)
        return
    assert _DB_PATH is not None, "SQLite path expected non-Postgres DATABASE_URL"
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
