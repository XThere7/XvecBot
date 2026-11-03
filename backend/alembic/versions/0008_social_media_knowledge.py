"""0008 agent-scoped social media knowledge.

Public social post imports are stored in `social_media_sources`. The post text
is indexed through the existing RAG tables as a virtual document, while
`chunks.agent_id` keeps that knowledge scoped to one agent.

Idempotent because startup also applies the same Postgres DDL from
`app/core/pg_schema.py`.
"""
from alembic import op

revision = "0008_social_media_knowledge"
down_revision = "0007_website_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS agent_id TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_agent "
        "ON chunks(workspace_id, agent_id)"
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_media_agent "
        "ON social_media_sources(agent_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_media_workspace "
        "ON social_media_sources(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_media_status "
        "ON social_media_sources(agent_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_media_hash "
        "ON social_media_sources(agent_id, content_hash)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_social_media_agent_url "
        "ON social_media_sources(workspace_id, agent_id, normalized_url)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_media_sources")
    op.execute("DROP INDEX IF EXISTS idx_chunks_agent")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS agent_id")
