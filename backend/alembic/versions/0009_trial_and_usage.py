"""0009 account trial, user plan and monthly chat usage.

Adds the account-level plan/trial state and the per-user monthly chat counter
used by the 21-day free-trial and TZS pricing update.

The trial is time-based: `users.plan` stays `free`; while `trial_ends_at` is in
the future the effective plan resolves to Pro-equivalent access. No scheduled
job mutates the row when the trial ends.

Idempotent because startup also applies the same Postgres DDL from
`app/core/pg_schema.py`.
"""
from alembic import op

revision = "0009_trial_and_usage"
down_revision = "0008_social_media_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "plan TEXT NOT NULL DEFAULT 'free'"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TEXT"
    )
    op.execute(
        "UPDATE users SET plan = 'free' WHERE plan IS NULL OR plan = ''"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_monthly (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            month         TEXT NOT NULL,
            chat_messages INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, month)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_monthly_user_month "
        "ON usage_monthly(user_id, month)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_usage_monthly_user_month")
    op.execute("DROP TABLE IF EXISTS usage_monthly")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS trial_ends_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan")
