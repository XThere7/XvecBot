"""
tests/test_ingestion.py
Unit tests for the ingestion pipeline components.
"""
import pytest
from ..ingestion.chunker import chunk_page, chunk_document
from ..ingestion.pdf_loader import PageContent
from ..ingestion.embedder import embed_texts, embed_query
from ..core.config import settings


class TestChunker:
    def test_short_page_single_chunk(self):
        """A page shorter than chunk_size produces exactly one chunk."""
        page = PageContent(page_number=1, text="Short text here.", char_count=16)
        chunks = chunk_page(page)
        assert len(chunks) == 1
        assert chunks[0].page == 1
        assert chunks[0].chunk_index == 0

    def test_long_page_multiple_chunks(self):
        """A long page produces multiple overlapping chunks."""
        long_text = " ".join([f"word{i}" for i in range(settings.chunk_size * 3)])
        page = PageContent(page_number=2, text=long_text, char_count=len(long_text))
        chunks = chunk_page(page)
        assert len(chunks) > 1
        # All chunks reference the same page
        assert all(c.page == 2 for c in chunks)
        # Chunk indices are sequential
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_chunk_preserves_page_number(self):
        """Page number is preserved through chunking."""
        page = PageContent(page_number=7, text="Some text on page seven.", char_count=24)
        chunks = chunk_page(page)
        assert all(c.page == 7 for c in chunks)

    def test_chunk_document_multiple_pages(self):
        """chunk_document processes all pages and returns flat list."""
        pages = [
            PageContent(page_number=i, text=f"Content for page {i} " * 10, char_count=100)
            for i in range(1, 4)
        ]
        all_chunks = chunk_document(pages)
        assert len(all_chunks) >= 3
        page_numbers = {c.page for c in all_chunks}
        assert page_numbers == {1, 2, 3}


REQUIRE_MODELS = pytest.mark.skipif(
    True,
    reason="Requires HuggingFace model download — run with internet access after: "
           "python -c \"from sentence_transformers import SentenceTransformer; "
           "SentenceTransformer('all-MiniLM-L6-v2')\"",
)


class TestEmbedder:
    @REQUIRE_MODELS
    def test_embed_texts_returns_correct_shape(self):
        """embed_texts returns one vector per input text."""
        texts = ["Hello world", "Another sentence"]
        embeddings = embed_texts(texts)
        assert len(embeddings) == 2
        assert len(embeddings[0]) == settings.embedding_dimension

    @REQUIRE_MODELS
    def test_embed_query_returns_vector(self):
        """embed_query returns a single normalised vector."""
        vec = embed_query("What is RAG?")
        assert isinstance(vec, list)
        assert len(vec) == settings.embedding_dimension

    @REQUIRE_MODELS
    def test_similar_texts_have_high_cosine_similarity(self):
        """Semantically similar texts should have cosine similarity > 0.7."""
        import math
        vecs = embed_texts(["The cat sat on the mat", "A cat is sitting on a mat"])
        a, b = vecs[0], vecs[1]
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x**2 for x in a))
        mag_b = math.sqrt(sum(x**2 for x in b))
        cosine = dot / (mag_a * mag_b + 1e-8)
        assert cosine > 0.7, f"Expected similarity > 0.7, got {cosine:.3f}"
