"""
storage/vector_store.py
All vector operations against the sqlite-vec virtual table (chunk_embeddings).
Provides insert, similarity search, and delete by document.
"""
import struct
from typing import Optional

import aiosqlite

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)


def _serialize_vector(vector: list[float]) -> bytes:
    """Pack a list of floats into the binary format sqlite-vec expects."""
    return struct.pack(f"{len(vector)}f", *vector)


async def insert_embedding(
    db: aiosqlite.Connection,
    chunk_id: str,
    embedding: list[float],
) -> None:
    """Store a single chunk embedding."""
    vec_bytes = _serialize_vector(embedding)
    await db.execute(
        "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, vec_bytes),
    )


async def search_similar(
    db: aiosqlite.Connection,
    query_vector: list[float],
    top_k: int = 20,
    document_id: Optional[str] = None,
) -> list[tuple[str, float]]:
    """
    KNN similarity search over chunk_embeddings.
    Returns list of (chunk_id, distance) sorted by distance ASC
    (lower = more similar for L2; we convert to a score 1/(1+d)).

    If document_id is provided, only chunks from that document are searched.
    sqlite-vec does not natively support WHERE on joined tables in vec0 queries,
    so we fetch top_k * 3 and filter in Python.
    """
    vec_bytes = _serialize_vector(query_vector)
    fetch_k = top_k * 3 if document_id else top_k

    query = """
        SELECT ce.chunk_id, ce.distance
        FROM chunk_embeddings ce
        WHERE ce.embedding MATCH ?
          AND k = ?
        ORDER BY ce.distance
    """
    async with db.execute(query, (vec_bytes, fetch_k)) as cur:
        rows = await cur.fetchall()

    results = []
    if document_id:
        # Filter by document via a join lookup
        for chunk_id, dist in rows:
            async with db.execute(
                "SELECT document_id FROM chunks WHERE id = ?", (chunk_id,)
            ) as c:
                chunk_row = await c.fetchone()
            if chunk_row and chunk_row["document_id"] == document_id:
                results.append((chunk_id, dist))
                if len(results) >= top_k:
                    break
    else:
        results = [(r["chunk_id"], r["distance"]) for r in rows]

    log.debug("Vector search complete", results=len(results))
    return results


async def delete_embeddings_for_document(
    db: aiosqlite.Connection,
    document_id: str,
) -> int:
    """Delete all embeddings whose chunk belongs to the given document."""
    async with db.execute(
        "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
    ) as cur:
        chunk_rows = await cur.fetchall()

    chunk_ids = [r["id"] for r in chunk_rows]
    if not chunk_ids:
        return 0

    placeholders = ",".join("?" * len(chunk_ids))
    await db.execute(
        f"DELETE FROM chunk_embeddings WHERE chunk_id IN ({placeholders})", chunk_ids
    )
    await db.commit()
    log.info("Embeddings deleted", document_id=document_id, count=len(chunk_ids))
    return len(chunk_ids)


async def delete_by_workspace(
    db: aiosqlite.Connection,
    workspace_id: str,
) -> int:
    """
    Delete all embeddings for chunks belonging to the given workspace.

    Same pattern as delete_embeddings_for_document: resolve chunk_ids
    relationally, then remove them from chunk_embeddings.

    Linkage: chunks -> documents (FK) -> workspace_documents via filename.
    (chunks.document_id references documents(id); workspace_documents rows
    share the same original filename as their documents row.)
    """
    async with db.execute(
        """SELECT c.id FROM chunks c
           JOIN documents d ON d.id = c.document_id
           JOIN workspace_documents wd ON wd.filename = d.filename
           WHERE wd.workspace_id = ?""",
        (workspace_id,),
    ) as cur:
        chunk_rows = await cur.fetchall()

    chunk_ids = [r["id"] for r in chunk_rows]
    if not chunk_ids:
        return 0

    placeholders = ",".join("?" * len(chunk_ids))
    await db.execute(
        f"DELETE FROM chunk_embeddings WHERE chunk_id IN ({placeholders})", chunk_ids
    )
    await db.commit()
    log.info(
        "Workspace embeddings deleted",
        workspace_id=workspace_id,
        count=len(chunk_ids),
    )
    return len(chunk_ids)
