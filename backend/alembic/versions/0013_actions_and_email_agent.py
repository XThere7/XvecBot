"""0013 agent actions, sales, support and email agent.

Creates the tables used by:
  * Agent Actions (agent_actions)
  * Sales & Lead Generation (leads)
  * Data Collection (data_collections, data_submissions)
  * Custom Forms (custom_forms, form_submissions)
  * Customer Support escalation (support_escalations)
  * Email Agent (email_integrations, incoming_emails, email_drafts,
    email_approvals, notification_messages)

The same DDL is applied idempotently at startup from the shared constants in
`app/models/engagement.py` and `app/models/email_agent.py`, so fresh SQLite
databases and Postgres deployments converge on the same schema.
"""
from alembic import op

import sys
from pathlib import Path

# `alembic.ini` may be invoked from the repository root, where the `app`
# package is not on sys.path. Add `backend/` before importing the shared DDL.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.email_agent import EMAIL_AGENT_TABLES_SQL
from app.models.engagement import ENGAGEMENT_TABLES_SQL

revision = "0013_actions_and_email_agent"
down_revision = "0012_admin_panel"
branch_labels = None
depends_on = None


def _run(block: str) -> None:
    for statement in (part.strip() for part in block.split(";")):
        if statement:
            op.execute(statement)


def upgrade() -> None:
    _run(ENGAGEMENT_TABLES_SQL)
    _run(EMAIL_AGENT_TABLES_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_messages")
    op.execute("DROP TABLE IF EXISTS email_approvals")
    op.execute("DROP TABLE IF EXISTS email_drafts")
    op.execute("DROP TABLE IF EXISTS incoming_emails")
    op.execute("DROP TABLE IF EXISTS email_integrations")
    op.execute("DROP TABLE IF EXISTS support_escalations")
    op.execute("DROP TABLE IF EXISTS form_submissions")
    op.execute("DROP TABLE IF EXISTS custom_forms")
    op.execute("DROP TABLE IF EXISTS data_submissions")
    op.execute("DROP TABLE IF EXISTS data_collections")
    op.execute("DROP TABLE IF EXISTS leads")
    op.execute("DROP TABLE IF EXISTS agent_actions")
