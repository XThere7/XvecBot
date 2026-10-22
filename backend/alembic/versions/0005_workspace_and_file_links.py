"""0005 workspace/file links (Stage 2 data-retention fixes).

Two additive columns that make "delete my workspace" actually delete the
customer's data:

  conversations.workspace_id
      A transcript that quotes a workspace's documents is owned by that
      workspace, even when no agent started it (the legacy /api/v1/query
      path). Without the link, those transcripts survived a workspace delete.

  documents.file_path
      Legacy direct uploads store their bytes on the upload volume. Without
      the path on the row, deleting the document left the file behind forever.

Both columns are nullable and additive: existing rows keep their data.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_workspace_and_file_links"
down_revision = "0004_developer_api_keys"
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "conversations" in inspector.get_table_names():
        if "workspace_id" not in _columns(inspector, "conversations"):
            op.execute("ALTER TABLE conversations ADD COLUMN workspace_id TEXT")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_workspace "
            "ON conversations(workspace_id)"
        )

    if "documents" in inspector.get_table_names():
        if "file_path" not in _columns(inspector, "documents"):
            op.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")


def downgrade() -> None:
    # SQLite before 3.35 cannot drop columns; the app tolerates both being
    # present, so the downgrade only drops the index.
    op.execute("DROP INDEX IF EXISTS idx_conversations_workspace")
