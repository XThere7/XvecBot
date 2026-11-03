"""0010 welcome email delivery marker.

Adds ``users.welcome_email_sent_at`` (nullable) used to guarantee the welcome
email is sent exactly once: the registration background task sets it only
after a successful send, and the UPDATE is guarded on the column still being
NULL.

Existing rows keep NULL and are never backfilled — pre-existing users never
receive a welcome email as a side effect of this migration.

Idempotent because startup also applies the same Postgres DDL from
`app/core/pg_schema.py`.
"""
from alembic import op

revision = "0010_welcome_email"
down_revision = "0009_trial_and_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_email_sent_at TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS welcome_email_sent_at"
    )
