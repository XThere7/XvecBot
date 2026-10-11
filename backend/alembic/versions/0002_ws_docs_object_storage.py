"""0002 object-storage columns on workspace_documents (Phase 2 presigned uploads)."""
from alembic import op

revision = "0002_ws_docs_object_storage"
down_revision = "0001_baseline_pg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspace_documents ADD COLUMN IF NOT EXISTS object_key TEXT")
    op.execute(
        "ALTER TABLE workspace_documents ADD COLUMN IF NOT EXISTS content_type TEXT"
    )
    op.execute("ALTER TABLE workspace_documents ADD COLUMN IF NOT EXISTS etag TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_documents DROP COLUMN IF EXISTS etag")
    op.execute("ALTER TABLE workspace_documents DROP COLUMN IF EXISTS content_type")
    op.execute("ALTER TABLE workspace_documents DROP COLUMN IF EXISTS object_key")
