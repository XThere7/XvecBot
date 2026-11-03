"""0012 admin panel foundation.

Adds:
  * users: role / permissions / last_login_at / suspended_at /
    suspended_reason / TOTP fields (totp_secret encrypted, recovery codes
    hashed).
  * audit_log (append-only; DB triggers block UPDATE/DELETE).
  * usage_events detail columns (user, agent, channel, model, status,
    latency, tokens, error code, month).
  * error_events, plan_changes, payments, platform_settings.

Idempotent because startup also applies the same Postgres DDL from
`app/core/pg_schema.py` (including the audit triggers).
"""
from alembic import op

revision = "0012_admin_panel"
down_revision = "0011_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_columns = {
        "role": "TEXT NOT NULL DEFAULT 'user'",
        "permissions": "TEXT",
        "last_login_at": "TEXT",
        "suspended_at": "TEXT",
        "suspended_reason": "TEXT",
        "totp_secret": "TEXT",
        "totp_enabled": "INTEGER NOT NULL DEFAULT 0",
        "recovery_codes": "TEXT",
        "totp_failed_at": "TEXT",
        "totp_failed_count": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in user_columns.items():
        op.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {definition}"
        )

    usage_columns = {
        "user_id": "TEXT",
        "agent_id": "TEXT",
        "channel": "TEXT",
        "model": "TEXT",
        "status": "TEXT",
        "latency_ms": "INTEGER",
        "prompt_tokens": "INTEGER",
        "completion_tokens": "INTEGER",
        "error_code": "TEXT",
        "month": "TEXT",
    }
    for column, definition in usage_columns.items():
        op.execute(
            f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {column} {definition}"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_created "
        "ON usage_events(created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id          TEXT PRIMARY KEY,
            ts          TEXT NOT NULL,
            actor_id    TEXT,
            actor_email TEXT,
            action      TEXT NOT NULL,
            target_type TEXT,
            target_id   TEXT,
            summary     TEXT NOT NULL,
            ip          TEXT,
            user_agent  TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS error_events (
            id             TEXT PRIMARY KEY,
            ts             TEXT NOT NULL,
            path           TEXT NOT NULL,
            status         INTEGER,
            exception_type TEXT,
            message        TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_events_ts ON error_events(ts)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_changes (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            from_plan  TEXT,
            to_plan    TEXT NOT NULL,
            reason     TEXT,
            changed_by TEXT NOT NULL,
            changed_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_plan_changes_user ON plan_changes(user_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount_tzs   INTEGER NOT NULL,
            method       TEXT NOT NULL,
            reference    TEXT,
            period_start TEXT,
            period_end   TEXT,
            recorded_by  TEXT NOT NULL,
            recorded_at  TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT,
            updated_by TEXT
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_settings")
    op.execute("DROP INDEX IF EXISTS idx_payments_user")
    op.execute("DROP TABLE IF EXISTS payments")
    op.execute("DROP INDEX IF EXISTS idx_plan_changes_user")
    op.execute("DROP TABLE IF EXISTS plan_changes")
    op.execute("DROP INDEX IF EXISTS idx_error_events_ts")
    op.execute("DROP TABLE IF EXISTS error_events")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_actor")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_ts")
    op.execute("DROP TABLE IF EXISTS audit_log")
    for column in (
        "role", "permissions", "last_login_at", "suspended_at",
        "suspended_reason", "totp_secret", "totp_enabled", "recovery_codes",
        "totp_failed_at", "totp_failed_count",
    ):
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}")
    for column in (
        "user_id", "agent_id", "channel", "model", "status", "latency_ms",
        "prompt_tokens", "completion_tokens", "error_code", "month",
    ):
        op.execute(f"ALTER TABLE usage_events DROP COLUMN IF EXISTS {column}")
