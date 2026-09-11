"""
retrieval/reranker.py
CrossEncoder reranker — second-stage precision scoring.

A CrossEncoder takes (query, passage) as a concatenated pair and outputs
a single relevance score. Unlike the bi-encoder (used in vector search),
it models the full interaction between query and passage, producing
significantly more accurate relevance judgements at the cost of speed.

Two-stage strategy:
  Stage 1 (fast):   Hybrid search returns top-20 candidates.
  Stage 2 (precise): CrossEncoder reranks those 20 to find the true top-5.
"""
from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import CrossEncoder

from ..core.config import settings
from ..core.logging import get_logger
from ..models.chunk import Chunk

log = get_logger(__name__)


@dataclass
class RerankResult:
    chunk: Chunk
    score: float
    rank: int


@lru_cache(maxsize=1)
def _get_reranker() -> CrossEncoder:
    """Load and cache the CrossEncoder model."""
    log.info("Loading reranker model", model=settings.reranker_model)
    model = CrossEncoder(settings.reranker_model)
    log.info("Reranker model loaded")
    return model


def rerank(
    query: str,
    chunks: list[Chunk],
    top_k: int = None,
) -> list[RerankResult]:
    """
    Rerank a list of candidate chunks using the CrossEncoder.

    Args:
        query:  User's question.
        chunks: Candidate chunks from hybrid search (typically top-20).
        top_k:  Number of chunks to keep after reranking.

    Returns:
        List of RerankResult sorted by score descending (rank 1 = most relevant).
    """
    if top_k is None:
        top_k = settings.rerank_top_k

    if not chunks:
        return []

    model = _get_reranker()

    # Build (query, passage) pairs for the CrossEncoder
    pairs = [[query, chunk.text] for chunk in chunks]

    # Predict scores — CrossEncoder outputs a single float per pair
    scores = model.predict(pairs, show_progress_bar=False)

    # Sort by score descending
    ranked = sorted(
        zip(chunks, scores.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )

    results = [
        RerankResult(chunk=chunk, score=score, rank=rank)
        for rank, (chunk, score) in enumerate(ranked[:top_k], start=1)
    ]

    log.info(
        "Reranking complete",
        input_count=len(chunks),
        output_count=len(results),
        top_score=results[0].score if results else None,
    )
    return results
