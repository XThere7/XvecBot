"""0004 developer API keys table (Phase 6 developer platform)."""
from alembic import op

revision = "0004_developer_api_keys"
down_revision = "0003_agent_icon_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS developer_api_keys (
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
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_keys_workspace "
        "ON developer_api_keys(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_keys_hash ON developer_api_keys(key_hash)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS developer_api_keys")
