"""
models/engagement.py
Pydantic schemas and SQL for the Agent Actions framework, Sales & Lead
Generation, Data Collection, Custom Forms and Customer Support escalation.

All tables are tenant-scoped through workspace_id and agent_id. The API and
services always verify both before returning a row.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Actions ──────────────────────────────────────────────────────────────────

ActionType = Literal[
    "lead_capture",
    "data_collection",
    "custom_forms",
    "knowledge_support",
]


class AgentActionCreate(BaseModel):
    action_type: ActionType
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AgentActionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    is_active: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class AgentActionRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    action_type: str
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    is_active: int
    config: dict[str, Any]
    created_at: str
    updated_at: str


class ActionCatalogEntry(BaseModel):
    action_type: str
    category: str
    name: str
    description: str
    required_feature: str
    plan_available: bool
    locked_reason: Optional[str] = None
    default_config: dict[str, Any]
    action: Optional[AgentActionRead] = None


class AgentActionsResponse(BaseModel):
    catalog: list[ActionCatalogEntry]
    plan_features: dict[str, bool]


# ── Leads ────────────────────────────────────────────────────────────────────

class LeadRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    action_id: Optional[str] = None
    conversation_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    interest: Optional[str] = None
    budget: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: dict[str, Any]
    status: str
    consent_given: int
    consent_text: Optional[str] = None
    created_at: str
    updated_at: str


class LeadListResponse(BaseModel):
    items: list[LeadRead]
    total: int
    limit: int
    offset: int


# ── Data Collections ─────────────────────────────────────────────────────────

class DataCollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    allow_partial: bool = False
    require_consent: bool = False


class DataCollectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    fields: Optional[list[dict[str, Any]]] = None
    is_active: Optional[bool] = None
    allow_partial: Optional[bool] = None
    require_consent: Optional[bool] = None


class DataCollectionRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    fields: list[dict[str, Any]]
    is_active: int
    allow_partial: int
    require_consent: int = 0
    submission_count: int = 0
    created_at: str
    updated_at: str


class DataSubmissionRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    collection_id: str
    conversation_id: Optional[str] = None
    data: dict[str, Any]
    status: str
    created_at: str


class DataSubmissionListResponse(BaseModel):
    items: list[DataSubmissionRead]
    total: int
    limit: int
    offset: int


# ── Custom Forms ─────────────────────────────────────────────────────────────

class CustomFormCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    submit_label: str = Field(default="Submit", max_length=60)
    is_active: bool = True
    require_consent: bool = True


class CustomFormUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    fields: Optional[list[dict[str, Any]]] = None
    submit_label: Optional[str] = Field(default=None, max_length=60)
    is_active: Optional[bool] = None
    require_consent: Optional[bool] = None


class CustomFormRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    title: str
    description: Optional[str] = None
    fields: list[dict[str, Any]]
    submit_label: str
    is_active: int
    require_consent: int = 1
    public_token: str
    submission_count: int = 0
    created_at: str
    updated_at: str


class PublicFormRead(BaseModel):
    title: str
    description: Optional[str] = None
    fields: list[dict[str, Any]]
    submit_label: str
    token: str
    agent_name: str
    require_consent: int = 1


class FormSubmissionRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    form_id: str
    conversation_id: Optional[str] = None
    data: dict[str, Any]
    status: str
    created_at: str


class FormSubmissionListResponse(BaseModel):
    items: list[FormSubmissionRead]
    total: int
    limit: int
    offset: int


# ── Customer support ─────────────────────────────────────────────────────────

class SupportEscalationRead(BaseModel):
    id: str
    workspace_id: str
    agent_id: str
    conversation_id: Optional[str] = None
    reason: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class SupportEscalationUpdate(BaseModel):
    status: Literal["open", "contacted", "closed"]


# ── SQL (shared by SQLite init_db and Postgres pg_schema) ────────────────────

ENGAGEMENT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_actions (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    action_type   TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT,
    instructions  TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    config        TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(agent_id, action_type)
);
CREATE INDEX IF NOT EXISTS idx_agent_actions_agent ON agent_actions(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_workspace ON agent_actions(workspace_id);

CREATE TABLE IF NOT EXISTS leads (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    action_id       TEXT REFERENCES agent_actions(id) ON DELETE SET NULL,
    conversation_id TEXT,
    full_name       TEXT,
    email           TEXT,
    phone           TEXT,
    company         TEXT,
    interest        TEXT,
    budget          TEXT,
    notes           TEXT,
    custom_fields   TEXT,
    status          TEXT NOT NULL DEFAULT 'complete',
    consent_given   INTEGER NOT NULL DEFAULT 0,
    consent_text    TEXT,
    dedupe_key      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(workspace_id, agent_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_leads_workspace_created
    ON leads(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_agent_created
    ON leads(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(workspace_id, email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(workspace_id, phone);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(agent_id, status);

CREATE TABLE IF NOT EXISTS data_collections (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    instructions  TEXT,
    fields        TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    allow_partial INTEGER NOT NULL DEFAULT 0,
    require_consent INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_collections_agent
    ON data_collections(agent_id, created_at);

CREATE TABLE IF NOT EXISTS data_submissions (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    collection_id   TEXT NOT NULL REFERENCES data_collections(id) ON DELETE CASCADE,
    conversation_id TEXT,
    data            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'complete',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_submissions_agent
    ON data_submissions(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_data_submissions_collection
    ON data_submissions(collection_id, created_at);

CREATE TABLE IF NOT EXISTS custom_forms (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    description   TEXT,
    fields        TEXT NOT NULL,
    submit_label  TEXT NOT NULL DEFAULT 'Submit',
    is_active     INTEGER NOT NULL DEFAULT 1,
    require_consent INTEGER NOT NULL DEFAULT 1,
    public_token  TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_forms_agent
    ON custom_forms(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_custom_forms_token
    ON custom_forms(public_token);

CREATE TABLE IF NOT EXISTS form_submissions (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    form_id         TEXT NOT NULL REFERENCES custom_forms(id) ON DELETE CASCADE,
    conversation_id TEXT,
    data            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'complete',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_form_submissions_agent
    ON form_submissions(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_form_submissions_form
    ON form_submissions(form_id, created_at);

CREATE TABLE IF NOT EXISTS support_escalations (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    conversation_id TEXT,
    reason          TEXT NOT NULL,
    contact_name    TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_support_escalations_agent
    ON support_escalations(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_support_escalations_status
    ON support_escalations(agent_id, status);
"""
