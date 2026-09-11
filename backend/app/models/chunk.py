"""
models/chunk.py
Data models for text chunks extracted from PDF pages.
"""
from pydantic import BaseModel


class Chunk(BaseModel):
    """A single text chunk from a PDF — carries its provenance."""
    id: str
    document_id: str
    page: int
    chunk_index: int
    text: str

    model_config = {"from_attributes": True}


class ChunkWithScore(BaseModel):
    """Chunk annotated with a retrieval or reranking score."""
    chunk: Chunk
    score: float
    source: str = "hybrid"   # "bm25" | "vector" | "hybrid" | "reranked"
