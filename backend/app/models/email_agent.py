"""
models/email_agent.py
Pydantic schemas and SQL for the Email Agent deployment.

Security notes:
  * Email credentials are never stored in plaintext. Only the Fernet-encrypted
    blob in `email_integrations.credentials_encrypted` is persisted, and the
    API never returns it.
  * Incoming messages are deduplicated by (integration_id, provider_message_id)
    so an email can never be processed twice.
  * Sending is simulated. The status is stored as `sent` together with
    `sent_simulated=1`, and the UI labels it "Sent (simulated)".
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EmailProvider = Literal["simulated", "imap", "gmail_oauth", "microsoft_oauth"]
DraftStatus = Literal[
    "processing", "draft_ready", "approved", "sent", "rejected", "failed"
]


class EmailIntegrationUpsert(BaseModel):
    provider: EmailProvider = "simulated"
    email_address: str = Field(..., min_length=3, max_length=254)
    display_name: Optional[str] = Field(default=None, max_length=120)
    automation_enabled: bool = True
    notification_phone: Optional[str] = Field(default=None, max_length=40)
    filters: dict[str, Any] = Field(default_factory=dict)
    # IMAP credentials are accepted only on write and encrypted immediately.
    imap_username: Optional[str] = Field(default=None, max_length=254)
    imap_password: Optional[str] = Field(default=None, max_length=500)


class EmailIntegrationRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    provider: str
    email_address: str
    display_name: Optional[str] = None
    status: str
    filters: dict[str, Any]
    automation_enabled: int
    notification_phone: Optional[str] = None
    has_credentials: bool
    created_at: str
    updated_at: str


class SimulatedEmailRequest(BaseModel):
    sender_name: str = Field(default="John Customer", max_length=120)
    sender_email: str = Field(..., min_length=3, max_length=254)
    subject: str = Field(..., min_length=1, max_length=300)
    body_text: str = Field(..., min_length=1, max_length=20000)
    provider_message_id: Optional[str] = Field(default=None, max_length=200)
    received_at: Optional[str] = Field(default=None, max_length=50)


class IncomingEmailRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    integration_id: str
    provider_message_id: str
    sender_name: Optional[str] = None
    sender_email: str
    subject: str
    body_text: str
    received_at: str
    status: str
    error_message: Optional[str] = None
    created_at: str


class EmailDraftRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    integration_id: str
    email_id: str
    body: str
    status: str
    model_used: Optional[str] = None
    error_message: Optional[str] = None
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    sent_simulated: int
    created_at: str
    updated_at: str
    email: Optional[IncomingEmailRead] = None


class EmailDraftListResponse(BaseModel):
    items: list[EmailDraftRead]
    total: int
    limit: int
    offset: int


class EmailApprovalRequest(BaseModel):
    body: Optional[str] = Field(default=None, max_length=30000)
    confirm_simulated_send: bool = False


class EmailRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class EmailDraftUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=30000)


class NotificationRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    channel: str
    provider: str
    recipient: str
    body: str
    status: str
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    simulated_at: Optional[str] = None


EMAIL_AGENT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS email_integrations (
    id                     TEXT PRIMARY KEY,
    workspace_id           TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id               TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    provider               TEXT NOT NULL DEFAULT 'simulated',
    email_address          TEXT NOT NULL,
    display_name           TEXT,
    credentials_encrypted  TEXT,
    status                 TEXT NOT NULL DEFAULT 'setup_required',
    filters                TEXT,
    automation_enabled     INTEGER NOT NULL DEFAULT 1,
    notification_phone     TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    UNIQUE(workspace_id, agent_id)
);
CREATE INDEX IF NOT EXISTS idx_email_integrations_agent
    ON email_integrations(agent_id);
CREATE INDEX IF NOT EXISTS idx_email_integrations_workspace
    ON email_integrations(workspace_id);

CREATE TABLE IF NOT EXISTS incoming_emails (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id            TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    integration_id      TEXT NOT NULL REFERENCES email_integrations(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    sender_name         TEXT,
    sender_email        TEXT NOT NULL,
    subject             TEXT NOT NULL,
    body_text           TEXT NOT NULL,
    received_at         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'received',
    error_message       TEXT,
    created_at          TEXT NOT NULL,
    UNIQUE(integration_id, provider_message_id)
);
CREATE INDEX IF NOT EXISTS idx_incoming_emails_agent
    ON incoming_emails(agent_id, received_at);
CREATE INDEX IF NOT EXISTS idx_incoming_emails_status
    ON incoming_emails(agent_id, status);

CREATE TABLE IF NOT EXISTS email_drafts (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    integration_id  TEXT NOT NULL REFERENCES email_integrations(id) ON DELETE CASCADE,
    email_id        TEXT NOT NULL REFERENCES incoming_emails(id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'processing',
    model_used      TEXT,
    error_message   TEXT,
    approved_at     TEXT,
    sent_at         TEXT,
    sent_simulated  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(email_id)
);
CREATE INDEX IF NOT EXISTS idx_email_drafts_agent
    ON email_drafts(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_email_drafts_status
    ON email_drafts(agent_id, status);

CREATE TABLE IF NOT EXISTS email_approvals (
    id          TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    email_id    TEXT NOT NULL REFERENCES incoming_emails(id) ON DELETE CASCADE,
    draft_id    TEXT NOT NULL REFERENCES email_drafts(id) ON DELETE CASCADE,
    action      TEXT NOT NULL,
    actor_id    TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_approvals_draft
    ON email_approvals(draft_id, created_at);

CREATE TABLE IF NOT EXISTS notification_messages (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    channel       TEXT NOT NULL DEFAULT 'sms',
    provider      TEXT NOT NULL DEFAULT 'simulated',
    recipient     TEXT NOT NULL,
    body          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'simulated',
    related_type  TEXT,
    related_id    TEXT,
    error_message TEXT,
    created_at    TEXT NOT NULL,
    simulated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_notification_messages_agent
    ON notification_messages(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_messages_related
    ON notification_messages(related_type, related_id);
"""
