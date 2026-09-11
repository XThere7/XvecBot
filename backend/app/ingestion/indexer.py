"""
ingestion/indexer.py
Writes chunks and their embeddings to the database in a single transaction.
Called as the final step of the ingestion pipeline.
"""
import aiosqlite

from ..core.logging import get_logger
from ..storage import sqlite as db_ops
from ..storage.vector_store import insert_embedding
from .chunker import TextChunk

log = get_logger(__name__)


async def index_chunks(
    db: aiosqlite.Connection,
    document_id: str,
    chunks: list[TextChunk],
    embeddings: list[list[float]],
) -> list[str]:
    """
    Persist chunks and their embeddings.
    Returns the list of chunk_ids in the same order as the input chunks.

    All writes happen in a single transaction — either all succeed or none do.
    """
    assert len(chunks) == len(embeddings), (
        f"Chunk/embedding count mismatch: {len(chunks)} vs {len(embeddings)}"
    )

    chunk_ids: list[str] = []

    log.info("Indexing chunks", document_id=document_id, count=len(chunks))
    for chunk, embedding in zip(chunks, embeddings):
        chunk_id = await db_ops.insert_chunk(
            db,
            document_id=document_id,
            page=chunk.page,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
        )
        await insert_embedding(db, chunk_id, embedding)
        chunk_ids.append(chunk_id)

    await db.commit()
    log.info("Chunks indexed", document_id=document_id, indexed=len(chunk_ids))
    return chunk_ids
