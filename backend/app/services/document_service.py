"""
services/document_service.py
Business logic for document ingestion.
Orchestrates: pdf_loader -> chunker -> embedder -> indexer -> DB status update.

The API layer calls this service and stays thin — no business logic in endpoints.
"""
import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite

from ..core.logging import get_logger
from ..ingestion.chunker import chunk_document
from ..ingestion.embedder import embed_texts
from ..ingestion.indexer import index_chunks
from ..ingestion.pdf_loader import load_pdf
from ..models.document import UploadResponse
from ..storage import sqlite as db_ops

log = get_logger(__name__)


async def ingest_document(
    db: aiosqlite.Connection,
    file_path: Path,
    original_filename: str,
) -> UploadResponse:
    """
    Full ingestion pipeline for a single PDF.

    Steps:
      1. Insert document record (status='processing')
      2. Extract text via PyMuPDF
      3. Chunk into overlapping passages
      4. Embed all chunks via SentenceTransformers
      5. Index chunks + embeddings to SQLite / sqlite-vec
      6. Update document status to 'ready'

    Args:
        db:                 Active DB connection.
        file_path:          Path to the saved PDF on disk.
        original_filename:  Filename to display in the UI.

    Returns:
        UploadResponse with document_id, page count, and chunk count.

    Raises:
        ValueError:  If the PDF has no extractable text.
        Exception:   Any other error; document status is set to 'error'.
    """
    file_size = file_path.stat().st_size

    # 1. Create document record
    doc_id = await db_ops.insert_document(
        db,
        filename=original_filename,
        total_pages=0,   # updated after PDF load
        file_size=file_size,
        # Remember where the bytes live so a delete can remove them.
        file_path=str(file_path),
    )

    try:
        # 2. Load PDF
        log.info("Ingestion: loading PDF", doc_id=doc_id)
        pdf_doc = await asyncio.get_event_loop().run_in_executor(
            None, load_pdf, file_path
        )

        # Update total_pages now we know it
        await db.execute(
            "UPDATE documents SET total_pages = ? WHERE id = ?",
            (pdf_doc.total_pages, doc_id),
        )
        await db.commit()

        # 3. Chunk
        log.info("Ingestion: chunking", doc_id=doc_id, pages=len(pdf_doc.pages))
        chunks = chunk_document(pdf_doc.pages)

        # 4. Embed (runs in thread pool — CPU-bound)
        log.info("Ingestion: embedding", doc_id=doc_id, chunks=len(chunks))
        texts = [c.text for c in chunks]
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None, embed_texts, texts
        )

        # 5. Index
        log.info("Ingestion: indexing", doc_id=doc_id)
        await index_chunks(db, doc_id, chunks, embeddings)

        # 6. Mark ready
        await db_ops.update_document_status(db, doc_id, "ready")

        log.info(
            "Ingestion complete",
            doc_id=doc_id,
            filename=original_filename,
            pages=pdf_doc.total_pages,
            chunks=len(chunks),
        )

        return UploadResponse(
            document_id=doc_id,
            filename=original_filename,
            total_pages=pdf_doc.total_pages,
            chunk_count=len(chunks),
        )

    except Exception as exc:
        log.error("Ingestion failed", doc_id=doc_id, error=str(exc))
        await db_ops.update_document_status(db, doc_id, "error")
        raise


async def delete_document_with_data(
    db: aiosqlite.Connection, doc_id: str
) -> bool:
    """
    Delete a document and all associated chunks/embeddings.
    Returns True if deleted, False if not found.
    """
    from pathlib import Path

    from ..storage.vector_store import delete_embeddings_for_document

    # Website pages own their shadow `documents` row. They must be removed by
    # disconnecting the website source; otherwise deleting the shadow here
    # would leave an "indexed" page with no chunks. Check before touching the
    # vector index.
    async with db.execute(
        "SELECT 1 FROM website_pages WHERE id = ?", (doc_id,)
    ) as cur:
        if await cur.fetchone() is not None:
            return False

    # Read the row first: the file path is needed after the row is gone.
    stored_path: Optional[str] = None
    try:
        async with db.execute(
            "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is not None:
            stored_path = row["file_path"] if "file_path" in row.keys() else None
    except Exception:
        stored_path = None

    # Embeddings first (FK constraint)
    await delete_embeddings_for_document(db, doc_id)
    # Chunks + document cascade via FK ON DELETE CASCADE
    deleted = await db_ops.delete_document(db, doc_id)
    if deleted:
        # Remove the uploaded bytes as well — otherwise the file stays on the
        # upload volume forever (orphan bytes + customer data kept after a
        # delete).
        if stored_path:
            try:
                Path(stored_path).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Document file cleanup failed", doc_id=doc_id, error=str(exc))
        log.info("Document deleted", doc_id=doc_id)
    return deleted
