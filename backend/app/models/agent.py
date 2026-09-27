"""
models/agent.py
Data models for Phase 3 (Agent Builder): agents and their chat transcripts.
Also documents the SQL schema for the three Phase 3 tables.

IMPORTANT — schema note
-----------------------
`agents` is a brand-new table. `conversations` and `messages` already exist from
Phase 1 (document Q&A transcripts) with a narrower schema:

    conversations(id, created_at)
    messages(id, conversation_id, role, content, citations, created_at)

Because `CREATE TABLE IF NOT EXISTS` is a no-op against an existing table, the
agent columns are added with ALTER TABLE ... ADD COLUMN instead of redefining the
tables. Existing rows and existing Phase 1 behaviour are preserved:

    conversations  + agent_id, title, updated_at   (agent_id NULL for legacy rows)

`messages` gains no new column at all: agent sources are stored in the existing
`citations` JSON array. `models/query.Citation` was extended with optional
`filename` and `chunk_index` so one field serves both phases.

An agent conversation is any conversations row with a non-NULL agent_id.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Agents ────────────────────────────────────────────────────────────────────

class Agent(BaseModel):
    """A configured AI personality bound to a workspace's knowledge base."""
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    model: str
    temperature: float = 0.7
    language: str = "English"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    description: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    language: str = Field(default="English", max_length=50)


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = Field(default=None, min_length=1)
    model: Optional[str] = Field(default=None, min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    language: Optional[str] = Field(default=None, max_length=50)
    is_active: Optional[bool] = None


class AgentRead(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    model: str
    temperature: float
    language: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Agent conversations & messages ────────────────────────────────────────────

class AgentConversation(BaseModel):
    """A chat thread between an end user and one agent."""
    id: str
    agent_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentConversationCreate(BaseModel):
    agent_id: str
    title: Optional[str] = Field(default=None, max_length=200)


class AgentConversationRead(BaseModel):
    id: str
    agent_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentMessage(BaseModel):
    """
    A single turn in an agent conversation.
    `citations` is a JSON array of Citation (see models/query.py) and is NULL
    for user messages. Shared with Phase 1 — there is no separate sources field.
    """
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    citations: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SQL schema ────────────────────────────────────────────────────────────────

CREATE_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    system_prompt TEXT NOT NULL,
    model         TEXT NOT NULL,
    temperature   REAL NOT NULL DEFAULT 0.7,
    language      TEXT NOT NULL DEFAULT 'English',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_workspace ON agents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_agents_active     ON agents(workspace_id, is_active);
"""

# Target shape for the pre-existing Phase 1 `conversations` table.
CREATE_AGENT_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT REFERENCES agents(id) ON DELETE CASCADE,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv      ON messages(conversation_id);
"""

# Target shape for the pre-existing Phase 1 `messages` table.
# `citations` is shared with Phase 1 and carries the agent sources as a JSON
# array of Citation (which now includes filename / chunk_index).
CREATE_AGENT_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content          TEXT NOT NULL,
    citations        TEXT,
    created_at       TEXT NOT NULL
);
"""

# Columns appended to the existing Phase 1 tables (see module docstring).
# messages needs no new column: it reuses the existing `citations` JSON array.
AGENT_CONVERSATION_COLUMNS = {
    "agent_id": "TEXT REFERENCES agents(id) ON DELETE CASCADE",
    "title": "TEXT",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

# An earlier revision added a duplicate `messages.sources` column. That database
# change is reverted here so a single source field is maintained; see
# DEPRECATED_COLUMNS in core/database.py for the cleanup migration.
DEPRECATED_MESSAGE_COLUMNS = {
    "messages": ("sources",),
}
