"""0011 password reset tokens and session invalidation.

Adds:

  * ``password_reset_tokens`` — single-use, 30-minute reset links stored as
    SHA-256 hashes only. ``used_at`` is set on consumption and also when a
    newer request supersedes an unused link.
  * ``users.password_changed_at`` — set on every successful reset. Access
    tokens issued with an ``iat`` claim older than this timestamp are rejected
    by ``get_current_user``; tokens without ``iat`` (issued before this
    deployment) remain valid, so existing sessions are not broken.

Idempotent because startup also applies the same Postgres DDL from
`app/core/pg_schema.py`.
"""
from alembic import op

revision = "0011_password_reset"
down_revision = "0010_welcome_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TEXT"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash    TEXT NOT NULL UNIQUE,
            created_at    TEXT NOT NULL,
            expires_at    TEXT NOT NULL,
            used_at       TEXT,
            requested_ip  TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash "
        "ON password_reset_tokens(token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user "
        "ON password_reset_tokens(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_password_reset_tokens_user")
    op.execute("DROP INDEX IF EXISTS idx_password_reset_tokens_hash")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at"
    )
