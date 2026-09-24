"""
retrieval/vector_search.py
Dense vector similarity search using the sqlite-vec virtual table.
Wraps the storage-layer search function and converts results to a
standardised VectorResult with rank and score.
"""
from dataclasses import dataclass
from typing import Optional

import aiosqlite

from ..core.config import settings
from ..core.logging import get_logger
from ..storage.vector_store import search_similar

log = get_logger(__name__)


@dataclass
class VectorResult:
    chunk_id: str
    score: float    # converted from distance: higher = more similar
    rank: int


async def vector_search(
    db: aiosqlite.Connection,
    query_vector: list[float],
    top_k: int = None,
    document_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> list[VectorResult]:
    """
    Perform cosine similarity search over chunk embeddings.

    sqlite-vec returns L2 distance (lower = more similar).
    We convert to a score via score = 1 / (1 + distance) so that
    higher score = more relevant, consistent with BM25.

    Args:
        db:            Active database connection.
        query_vector:  Embedded query from the embedder.
        top_k:         Number of results to return.
        document_id:   Optionally scope search to one document.
        workspace_id:  Optionally scope search to one workspace (multi-tenant).
                       None keeps the original single-tenant behaviour.

    Returns:
        List of VectorResult sorted by score descending.
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    raw_results = await search_similar(
        db,
        query_vector=query_vector,
        top_k=top_k,
        document_id=document_id,
        workspace_id=workspace_id,
    )

    results = []
    for rank, (chunk_id, distance) in enumerate(raw_results, start=1):
        score = 1.0 / (1.0 + distance)
        results.append(VectorResult(chunk_id=chunk_id, score=score, rank=rank))

    log.debug("Vector search complete", results=len(results))
    return results
