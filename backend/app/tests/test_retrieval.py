"""
tests/test_retrieval.py
Unit tests for BM25, reranker, and RRF fusion.
"""
import pytest
from ..retrieval.bm25 import bm25_search
from ..retrieval.reranker import rerank
from ..models.chunk import Chunk


def _make_chunk(chunk_id: str, text: str, page: int = 1) -> Chunk:
    return Chunk(id=chunk_id, document_id="doc1", page=page, chunk_index=0, text=text)


class TestBM25:
    def test_returns_ranked_results(self):
        chunks = [
            _make_chunk("c1", "RAG stands for Retrieval Augmented Generation", page=1),
            _make_chunk("c2", "The weather is sunny today", page=2),
            _make_chunk("c3", "Retrieval systems use BM25 and vector search", page=3),
        ]
        results = bm25_search("What is retrieval augmented generation?", chunks)
        assert len(results) > 0
        # Most relevant chunk should rank first
        top_id = results[0].chunk_id
        assert top_id in ("c1", "c3")

    def test_empty_corpus_returns_empty(self):
        results = bm25_search("any query", [])
        assert results == []

    def test_rank_is_sequential(self):
        chunks = [_make_chunk(f"c{i}", f"Document about topic {i}") for i in range(5)]
        results = bm25_search("topic", chunks)
        ranks = [r.rank for r in results]
        assert ranks == list(range(1, len(results) + 1))


REQUIRE_MODELS = pytest.mark.skipif(
    True,
    reason="Requires HuggingFace model download — run with internet access.",
)


class TestReranker:
    @REQUIRE_MODELS
    def test_reranks_and_trims_to_top_k(self):
        chunks = [
            _make_chunk("c1", "LangGraph is used for AI pipeline orchestration", page=1),
            _make_chunk("c2", "The sun rises in the east", page=2),
            _make_chunk("c3", "SQLite-vec enables vector search inside SQLite", page=3),
            _make_chunk("c4", "FastAPI provides fast async web API development", page=4),
            _make_chunk("c5", "Cross-encoders rerank passages for better precision", page=5),
        ]
        results = rerank("How does vector search work in SQLite?", chunks, top_k=2)
        assert len(results) == 2
        assert results[0].rank == 1
        assert results[1].rank == 2
        # Most relevant should be c3 or c5
        assert results[0].chunk.id in ("c3", "c5")

    def test_empty_input_returns_empty(self):
        results = rerank("any query", [])
        assert results == []
