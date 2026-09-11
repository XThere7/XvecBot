"""
ingestion/embedder.py
Encodes text chunks into dense embedding vectors using SentenceTransformers.
The model is loaded once and cached for the process lifetime.
Both ingestion (batch) and query-time (single) embedding go through here.
"""
from functools import lru_cache
from typing import Union

from sentence_transformers import SentenceTransformer

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load and cache the embedding model on first call."""
    log.info("Loading embedding model", model=settings.embedding_model)
    model = SentenceTransformer(settings.embedding_model)
    log.info("Embedding model loaded", dimension=settings.embedding_dimension)
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Encode a batch of texts into embedding vectors.
    Returns a list of float lists, one per input text.
    Batch encoding is significantly faster than encoding one-by-one.
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,   # L2-normalise for cosine similarity
    )
    return [emb.tolist() for emb in embeddings]


def embed_query(query: str) -> list[float]:
    """
    Encode a single query string. Identical normalisation to embed_texts
    so cosine similarity is directly comparable.
    """
    model = _get_model()
    embedding = model.encode(
        query,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embedding.tolist()
