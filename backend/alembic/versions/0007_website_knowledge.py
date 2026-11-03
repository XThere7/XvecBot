"""0007 website-to-knowledge sources, pages and sync jobs.

Adds the three website crawler tables. Every crawled page is indexed as a
virtual document through the existing RAG tables; these tables only own the
source metadata and crawl state.

All statements are idempotent because startup also applies the same Postgres
DDL from `app/core/pg_schema.py`.
"""
from alembic import op

revision = "0007_website_knowledge"
down_revision = "0006_subscriptions_and_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_sources_workspace "
        "ON website_sources(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_sources_due "
        "ON website_sources(refresh_policy, next_sync_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_website_sources_workspace_url "
        "ON website_sources(workspace_id, url)"
    )

    op.execute(
        """
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
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_pages_source "
        "ON website_pages(source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_pages_workspace "
        "ON website_pages(workspace_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_website_pages_source_url "
        "ON website_pages(source_id, url)"
    )

    op.execute(
        """
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
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_sync_jobs_source "
        "ON website_sync_jobs(source_id, started_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_website_sync_jobs_workspace "
        "ON website_sync_jobs(workspace_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_website_sync_jobs_workspace")
    op.execute("DROP INDEX IF EXISTS idx_website_sync_jobs_source")
    op.execute("DROP TABLE IF EXISTS website_sync_jobs")
    op.execute("DROP INDEX IF EXISTS idx_website_pages_source_url")
    op.execute("DROP INDEX IF EXISTS idx_website_pages_workspace")
    op.execute("DROP INDEX IF EXISTS idx_website_pages_source")
    op.execute("DROP TABLE IF EXISTS website_pages")
    op.execute("DROP INDEX IF EXISTS idx_website_sources_workspace_url")
    op.execute("DROP INDEX IF EXISTS idx_website_sources_due")
    op.execute("DROP INDEX IF EXISTS idx_website_sources_workspace")
    op.execute("DROP TABLE IF EXISTS website_sources")
