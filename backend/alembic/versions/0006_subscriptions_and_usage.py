"""0006 subscriptions and usage metering.

Adds the subscription state to workspaces and an append-only AI-response
ledger. Existing workspaces become Free (the column default) and keep every
row of data; historical assistant messages are not backfilled because the
product has not been billing anyone before this release.

Calendar-month usage periods and all limit checks live in
`app/services/plan_service.py`; this migration only creates storage.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_subscriptions_and_usage"
down_revision = "0005_workspace_and_file_links"
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "workspaces" in inspector.get_table_names():
        existing = _columns(inspector, "workspaces")
        if "plan" not in existing:
            op.execute(
                "ALTER TABLE workspaces ADD COLUMN plan "
                "TEXT NOT NULL DEFAULT 'free'"
            )
        if "plan_started_at" not in existing:
            op.execute(
                "ALTER TABLE workspaces ADD COLUMN plan_started_at TEXT"
            )
        # New rows get a start date; existing rows inherit their creation date
        # so the billing page can say "Free since <date>".
        op.execute(
            "UPDATE workspaces SET plan = 'free' "
            "WHERE plan IS NULL OR plan = ''"
        )
        op.execute(
            "UPDATE workspaces SET plan_started_at = created_at "
            "WHERE plan_started_at IS NULL"
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
            id           TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            kind         TEXT NOT NULL,
            quantity     INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_ws_kind_created "
        "ON usage_events(workspace_id, kind, created_at)"
    )


def downgrade() -> None:
    # SQLite before 3.35 cannot drop columns; the app tolerates the two
    # workspace columns being present, so only the ledger is removed.
    op.execute("DROP INDEX IF EXISTS idx_usage_events_ws_kind_created")
    op.execute("DROP TABLE IF EXISTS usage_events")
