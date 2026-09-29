"""
models/embed_token.py
Data model for Phase 4 (embeddable widget): public embed tokens.

An embed token is an opaque random string that maps to one agent and lets any
website embed that agent as a chat bubble — no JWT required. Origin allow-listing
and per-token request counting are stored here.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AgentEmbedToken(BaseModel):
    """A public embed token mapping to one agent."""
    id: str
    agent_id: str
    token: str
    label: Optional[str] = None
    is_active: bool = True
    allowed_origins: Optional[str] = None   # JSON array string; None = allow all
    request_count: int = 0
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentEmbedTokenCreate(BaseModel):
    agent_id: str
    label: Optional[str] = None
    allowed_origins: Optional[list[str]] = None


class PublicAgentInfo(BaseModel):
    """The only agent fields the public widget is allowed to see."""
    name: str
    description: Optional[str] = None
    language: str
