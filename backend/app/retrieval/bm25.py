"""
retrieval/bm25.py
BM25 keyword search over all indexed chunks.
The BM25 index is built in-memory at query time from the chunk corpus.
For large corpora this can be cached; for portfolio scale it is fast enough.
"""
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from ..core.config import settings
from ..core.logging import get_logger
from ..models.chunk import Chunk

log = get_logger(__name__)


@dataclass
class BM25Result:
    chunk_id: str
    score: float
    rank: int


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return text.lower().split()


def bm25_search(
    query: str,
    chunks: list[Chunk],
    top_k: int = None,
) -> list[BM25Result]:
    """
    Run BM25 over the provided chunk corpus.

    Args:
        query:   User's natural-language question.
        chunks:  Full corpus of chunks to search over.
        top_k:   Maximum results to return.

    Returns:
        List of BM25Result sorted by score descending (rank 1 = best).
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    if not chunks:
        return []

    tokenized_corpus = [_tokenize(c.text) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    # Pair (chunk, score) and sort descending
    scored = sorted(
        zip(chunks, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    results = []
    for rank, (chunk, score) in enumerate(scored[:top_k], start=1):
        if score > 0:  # Skip zero-score chunks
            results.append(BM25Result(chunk_id=chunk.id, score=float(score), rank=rank))

    log.debug(
        "BM25 search complete",
        query_tokens=len(tokenized_query),
        corpus_size=len(chunks),
        results=len(results),
    )
    return results
