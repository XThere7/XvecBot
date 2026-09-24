"""
graph/state.py
LangGraph state definition for the RAG pipeline.
Every node reads from and writes to this typed dictionary.
Using TypedDict makes the data flow explicit and catches errors early.
"""
from typing import Optional, TypedDict

from ..models.chunk import Chunk
from ..models.query import Citation


class RAGState(TypedDict):
    """
    The complete state that flows through the RAG LangGraph pipeline.

    Fields are populated progressively:
      retrieve_node    -> retrieved_chunks
      rerank_node      -> reranked_chunks
      grounding_node   -> grounded, grounding_message
      generate_node    -> answer
      citation_node    -> citations
    """
    # Input
    query: str
    conversation_id: str
    document_id: Optional[str]
    workspace_id: Optional[str]      # multi-tenant scope; None = single-tenant

    # Retrieval stage
    query_vector: Optional[list[float]]
    retrieved_chunk_ids: list[str]       # chunk IDs from hybrid search
    retrieved_chunks: list[Chunk]        # full Chunk objects
    retrieved_count: int

    # Reranking stage
    reranked_chunks: list[Chunk]         # top-K after cross-encoder

    # Grounding stage
    grounded: bool
    grounding_message: Optional[str]     # set if grounding fails

    # Generation stage
    context: str                         # formatted context string for LLM
    answer: str

    # Citation stage
    citations: list[Citation]
