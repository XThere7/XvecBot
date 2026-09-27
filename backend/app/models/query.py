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
    """
    A source backing an answer. Stored as a JSON array in messages.citations.

    Shared by Phase 1 (document Q&A) and Phase 3 (agents), so every field is
    optional except the chunk identity:

      - Phase 1 emits page, chunk_id, text_preview.
      - Phase 3 (agents) adds filename and chunk_index, and may omit page for
        non-paginated sources (.txt / .docx).
    """
    chunk_id: str
    page: Optional[int] = None
    text_preview: str = ""
    filename: Optional[str] = None
    chunk_index: Optional[int] = None


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
