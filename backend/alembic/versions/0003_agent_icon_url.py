"""0003 agent icon_url column (bot avatar upload)."""
from alembic import op

revision = "0003_agent_icon_url"
down_revision = "0002_ws_docs_object_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS icon_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS icon_url")
