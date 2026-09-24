"""
services/workspace_training_service.py
Trains a single workspace document through the existing ingestion pipeline:
extract -> chunk -> embed -> index, scoped to the workspace's document row.

Reuses (unmodified): chunker, embedder, indexer, pdf_loader.extract_text_from_file.
CPU-heavy steps run via asyncio.to_thread so the event loop stays responsive.
"""
import asyncio
from typing import Optional

import aiosqlite

from ..core.logging import get_logger
from ..ingestion.chunker import chunk_document
from ..ingestion.embedder import embed_texts
from ..ingestion.indexer import index_chunks
from ..ingestion.pdf_loader import PageContent, extract_text_from_file
from ..storage import vector_store

log = get_logger(__name__)


async def _set_status(
    db: aiosqlite.Connection,
    doc_id: str,
    status: str,
    chunk_count: Optional[int] = None,
) -> None:
    if chunk_count is None:
        await db.execute(
            "UPDATE workspace_documents SET status = ? WHERE id = ?",
            (status, doc_id),
        )
    else:
        await db.execute(
            "UPDATE workspace_documents SET status = ?, chunk_count = ? WHERE id = ?",
            (status, chunk_count, doc_id),
        )
    await db.commit()


async def _ensure_chunk_metadata_columns(db: aiosqlite.Connection) -> None:
    """
    Add workspace_id / doc_id columns to chunks if missing.
    SQLite has no ALTER TABLE ... ADD COLUMN IF NOT EXISTS, so guard via PRAGMA —
    existing data is untouched, columns are only added when absent.
    """
    async with db.execute("PRAGMA table_info(chunks)") as cur:
        existing = {row["name"] for row in await cur.fetchall()}
    for column in ("workspace_id", "doc_id"):
        if column not in existing:
            await db.execute(f"ALTER TABLE chunks ADD COLUMN {column} TEXT")
            log.info("Schema extended: chunks column added", column=column)
    await db.commit()


async def _ensure_documents_row(db: aiosqlite.Connection, doc: dict) -> None:
    """
    Create a shadow `documents` row for this workspace document.
    chunks.document_id has a FK to documents(id), and the existing delete paths
    (delete_embeddings_for_document / delete_by_workspace) join through it.
    """
    async with db.execute(
        "SELECT id FROM documents WHERE id = ?", (doc["id"],)
    ) as cur:
        if await cur.fetchone() is None:
            await db.execute(
                """INSERT INTO documents (id, filename, upload_date, total_pages, file_size, status)
                   VALUES (?, ?, ?, 0, ?, 'ready')""",
                (doc["id"], doc["filename"], doc["created_at"], doc["size_bytes"]),
            )
            await db.commit()
            log.debug("Shadow documents row created", doc_id=doc["id"])


async def _clear_previous_index(db: aiosqlite.Connection, doc_id: str) -> None:
    """Remove any prior chunks/embeddings for this document (idempotent re-train)."""
    await vector_store.delete_embeddings_for_document(db, doc_id)
    await db.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
    await db.commit()


async def train_workspace_document(doc_id: str, db: aiosqlite.Connection) -> None:
    """
    Full training pipeline for one workspace document.

    Status flow: uploaded -> processing -> ready | failed.
    Never raises — on any error the document is marked 'failed' and logged.
    """
    async with db.execute(
        "SELECT * FROM workspace_documents WHERE id = ?", (doc_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        log.warning("Training skipped: document not found", doc_id=doc_id)
        return
    doc = dict(row)

    try:
        await _set_status(db, doc_id, "processing")

        # 1. Extract text (file I/O + parsing — off the event loop)
        text = await asyncio.to_thread(
            extract_text_from_file, doc["file_path"], doc["file_type"]
        )
        if not text.strip():
            log.warning(
                "Training failed: no extractable text",
                doc_id=doc_id,
                filename=doc["filename"],
            )
            await _set_status(db, doc_id, "failed")
            return

        # 2. Chunk (CPU work — off the event loop)
        pages = [PageContent(page_number=1, text=text, char_count=len(text))]
        chunks = await asyncio.to_thread(chunk_document, pages)
        if not chunks:
            log.warning("Training failed: chunking produced nothing", doc_id=doc_id)
            await _set_status(db, doc_id, "failed", chunk_count=0)
            return

        # 3. Embed (CPU-heavy — off the event loop)
        embeddings = await asyncio.to_thread(embed_texts, [c.text for c in chunks])

        # 4. Storage prep: metadata columns, shadow documents row, idempotent re-train
        await _ensure_chunk_metadata_columns(db)
        await _ensure_documents_row(db, doc)
        await _clear_previous_index(db, doc_id)

        # 5. Index chunks + embeddings with workspace metadata
        chunk_ids = await index_chunks(
            db,
            doc_id,
            chunks,
            embeddings,
            metadata={
                "workspace_id": doc["workspace_id"],
                "doc_id": doc["id"],
                "filename": doc["filename"],
            },
        )

        # 6. Mark ready
        await _set_status(db, doc_id, "ready", chunk_count=len(chunk_ids))
        log.info(
            "Training complete",
            doc_id=doc_id,
            workspace_id=doc["workspace_id"],
            filename=doc["filename"],
            chunks=len(chunk_ids),
        )

    except Exception as exc:
        log.error("Training failed", doc_id=doc_id, error=str(exc))
        try:
            await _set_status(db, doc_id, "failed")
        except Exception as status_exc:
            log.error(
                "Could not mark document failed",
                doc_id=doc_id,
                error=str(status_exc),
            )
