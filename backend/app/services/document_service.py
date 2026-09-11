"""
services/document_service.py
Business logic for document ingestion.
Orchestrates: pdf_loader -> chunker -> embedder -> indexer -> DB status update.

The API layer calls this service and stays thin — no business logic in endpoints.
"""
import asyncio
from pathlib import Path

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
    from ..storage.vector_store import delete_embeddings_for_document

    # Embeddings first (FK constraint)
    await delete_embeddings_for_document(db, doc_id)
    # Chunks + document cascade via FK ON DELETE CASCADE
    deleted = await db_ops.delete_document(db, doc_id)
    if deleted:
        log.info("Document deleted", doc_id=doc_id)
    return deleted
