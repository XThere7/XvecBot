"""
retrieval/hybrid_search.py
Reciprocal Rank Fusion (RRF) over BM25 + vector search results.

RRF formula per chunk:
    score = sum(1 / (k + rank_i))   for each retrieval method i

where k=60 is a standard smoothing constant that prevents very high-ranked
items from dominating. The fused scores are then sorted descending.

This is the retrieval pattern used by production teams at Google, Cohere,
and in the MTEB/BEIR benchmarks — it consistently outperforms either method
alone across diverse query types.
"""
from dataclasses import dataclass
from typing import Optional

import aiosqlite

from ..core.config import settings
from ..core.logging import get_logger
from ..models.chunk import Chunk
from ..storage import sqlite as db_ops
from .bm25 import BM25Result, bm25_search
from .vector_search import VectorResult, vector_search

log = get_logger(__name__)


@dataclass
class HybridResult:
    chunk_id: str
    rrf_score: float
    rank: int
    bm25_rank: Optional[int] = None
    vector_rank: Optional[int] = None


def _rrf_score(rank: int, k: int = None) -> float:
    if k is None:
        k = settings.rrf_k
    return 1.0 / (k + rank)


async def hybrid_search(
    db: aiosqlite.Connection,
    query: str,
    query_vector: list[float],
    top_k: int = None,
    document_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> list[HybridResult]:
    """
    Fuse BM25 and vector search results using Reciprocal Rank Fusion.

    Args:
        db:            Active DB connection.
        query:         Raw user question (for BM25).
        query_vector:  Embedded query (for vector search).
        top_k:         Final number of chunks to return after fusion.
        document_id:   Scope retrieval to a single document.
        workspace_id:  Scope retrieval to a single workspace (multi-tenant).
                       None keeps the original single-tenant behaviour.

    Returns:
        List of HybridResult sorted by RRF score descending.
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    # Fetch corpus for BM25 (in-memory build), scoped to workspace/document
    all_chunks: list[Chunk] = await db_ops.get_all_chunks(
        db, document_id=document_id, workspace_id=workspace_id
    )
    if not all_chunks:
        log.warning(
            "No chunks found for hybrid search",
            document_id=document_id,
            workspace_id=workspace_id,
        )
        return []

    # Run both searches in parallel conceptually (sequential here — fast enough)
    bm25_results: list[BM25Result] = bm25_search(
        query, all_chunks, top_k=top_k, workspace_id=workspace_id
    )
    vector_results: list[VectorResult] = await vector_search(
        db, query_vector, top_k=top_k, document_id=document_id, workspace_id=workspace_id
    )

    # Build rank maps: chunk_id -> rank
    bm25_ranks: dict[str, int] = {r.chunk_id: r.rank for r in bm25_results}
    vector_ranks: dict[str, int] = {r.chunk_id: r.rank for r in vector_results}

    # Gather all candidate chunk IDs
    all_ids = set(bm25_ranks) | set(vector_ranks)

    # Compute RRF score for each candidate
    # Chunks missing from one method get penalised with rank = top_k + 1
    penalty_rank = top_k + 1
    fused: dict[str, dict] = {}
    for chunk_id in all_ids:
        bm25_rank = bm25_ranks.get(chunk_id, penalty_rank)
        vec_rank = vector_ranks.get(chunk_id, penalty_rank)
        rrf = _rrf_score(bm25_rank) + _rrf_score(vec_rank)
        fused[chunk_id] = {
            "rrf_score": rrf,
            "bm25_rank": bm25_ranks.get(chunk_id),
            "vector_rank": vector_ranks.get(chunk_id),
        }

    # Sort by RRF score descending and take top_k
    sorted_ids = sorted(fused, key=lambda cid: fused[cid]["rrf_score"], reverse=True)

    results = []
    for rank, chunk_id in enumerate(sorted_ids[:top_k], start=1):
        d = fused[chunk_id]
        results.append(
            HybridResult(
                chunk_id=chunk_id,
                rrf_score=d["rrf_score"],
                rank=rank,
                bm25_rank=d["bm25_rank"],
                vector_rank=d["vector_rank"],
            )
        )

    log.info(
        "Hybrid search complete",
        bm25_candidates=len(bm25_results),
        vector_candidates=len(vector_results),
        fused_candidates=len(all_ids),
        returned=len(results),
    )
    return results
