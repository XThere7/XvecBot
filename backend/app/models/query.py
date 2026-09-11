"""
models/query.py
Request and response shapes for the /query endpoint.
"""
from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    conversation_id: Optional[str] = None
    document_id: Optional[str] = None     # scope to a single document
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    page: int
    chunk_id: str
    text_preview: str    # first 200 chars of the cited chunk


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conversation_id: str
    grounded: bool        # True = answer is supported by retrieved context
    retrieved_count: int  # how many chunks were retrieved before reranking


class ConversationMessage(BaseModel):
    role: str
    content: str
    citations: list[Citation] = []


class ConversationHistory(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]
