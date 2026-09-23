"""
models/workspace.py
Data models for multi-tenant users, workspaces, and workspace documents.
Also documents the SQL schema for the three Phase 2 tables.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    """A registered customer (tenant)."""
    id: str
    email: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)


class UserRead(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Workspace(BaseModel):
    """An isolated tenant workspace — owns its documents and vector data."""
    id: str
    name: str
    description: Optional[str] = None
    system_prompt: str = "You are a helpful assistant."
    owner_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: str = "You are a helpful assistant."


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = None


class WorkspaceRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    owner_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceDocument(BaseModel):
    """A file uploaded into a workspace, tracked through processing."""
    id: str
    workspace_id: str
    filename: str
    file_path: str
    file_type: Literal["pdf", "txt", "docx"]
    size_bytes: int = 0
    status: Literal["uploaded", "processing", "ready", "failed"] = "uploaded"
    chunk_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceDocumentRead(BaseModel):
    id: str
    workspace_id: str
    filename: str
    file_type: str
    size_bytes: int
    status: str
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SQL schema (mirrored in core/database.py init_db) ────────────────────────

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
"""

CREATE_WORKSPACES = """
CREATE TABLE IF NOT EXISTS workspaces (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    system_prompt  TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
    owner_id       TEXT NOT NULL REFERENCES users(id),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);
"""

CREATE_WORKSPACE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS workspace_documents (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'uploaded',
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_docs_ws ON workspace_documents(workspace_id);
"""
