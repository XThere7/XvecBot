"""0001 Postgres baseline — mirrors app/core/pg_schema.py (Neon production).

11 tables, final columns (no ALTER needed on fresh DB), pgvector extension,
chunk_embeddings as vector(384) table, best-effort HNSW index.
"""
from alembic import op

revision = "0001_baseline_pg"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Order matters for REFERENCES. IF NOT EXISTS everywhere.
    op.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            total_pages INTEGER NOT NULL,
            file_size   INTEGER NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'processing'
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS workspaces (
            id             TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            description    TEXT,
            system_prompt  TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
            owner_id       TEXT NOT NULL REFERENCES users(id),
            created_at     TEXT NOT NULL
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id)")
    op.execute(
        """CREATE TABLE IF NOT EXISTS workspace_documents (
            id            TEXT PRIMARY KEY,
            workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            filename      TEXT NOT NULL,
            file_path     TEXT NOT NULL,
            file_type     TEXT NOT NULL,
            size_bytes    INTEGER NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'uploaded',
            chunk_count   INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_docs_ws "
        "ON workspace_documents(workspace_id)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS agents (
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
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_workspace ON agents(workspace_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agents_active "
        "ON agents(workspace_id, is_active)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            agent_id   TEXT REFERENCES agents(id) ON DELETE CASCADE,
            title      TEXT,
            updated_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id              TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content         TEXT NOT NULL,
            citations       TEXT,
            created_at      TEXT NOT NULL
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)")
    op.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            id          TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page        INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text        TEXT NOT NULL,
            workspace_id TEXT,
            doc_id       TEXT
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(document_id, page)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON chunks(workspace_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)")
    op.execute(
        """CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id     TEXT PRIMARY KEY,
            workspace_id TEXT,
            doc_id       TEXT,
            embedding    vector(384)
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_workspace "
        "ON chunk_embeddings(workspace_id)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS agent_embed_tokens (
            id            TEXT PRIMARY KEY,
            agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            token         TEXT NOT NULL UNIQUE,
            label         TEXT,
            is_active     INTEGER NOT NULL DEFAULT 1,
            allowed_origins TEXT,
            request_count INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            last_used_at  TEXT
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embed_tokens_agent "
        "ON agent_embed_tokens(agent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embed_tokens_token "
        "ON agent_embed_tokens(token)"
    )
    # Best-effort ANN index — failures must not fail the migration on
    # pgvector builds without HNSW; init_db wraps it in try/except too.
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw "
            "ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)"
        )
    except Exception:
        pass


def downgrade() -> None:
    for t in (
        "agent_embed_tokens",
        "chunk_embeddings",
        "chunks",
        "messages",
        "conversations",
        "agents",
        "workspace_documents",
        "workspaces",
        "users",
        "documents",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t}")
