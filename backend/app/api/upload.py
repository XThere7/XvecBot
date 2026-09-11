"""
api/upload.py
Document upload and management endpoints.
All business logic is delegated to document_service — endpoints stay thin.
"""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..models.document import DocumentList, DocumentRead, UploadResponse
from ..services.document_service import delete_document_with_data, ingest_document
from ..storage import sqlite as db_ops
from .deps import verify_api_key

log = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a PDF document",
)
async def upload_document(
    file: UploadFile = File(...),
    _: str = Depends(verify_api_key),
):
    """
    Upload a PDF file. The system will:
    1. Save the file to disk
    2. Extract text (PyMuPDF)
    3. Chunk and embed the text
    4. Index chunks into SQLite + SQLite-vec

    Returns the document_id and ingestion stats.
    """
    # Validate content type — allow application/pdf or extension fallback
    # Some browsers may send application/octet-stream for PDFs
    original_filename = file.filename or "document.pdf"
    is_pdf_ext = original_filename.lower().endswith(".pdf")
    if file.content_type not in ALLOWED_CONTENT_TYPES and not is_pdf_ext:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only PDF files are accepted. Got: {file.content_type}",
        )

    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE_MB}MB.",
        )

    # Save to uploads directory with a unique name (sanitize filename)
    safe_original = Path(original_filename).name  # strip any path components
    safe_name = f"{uuid.uuid4()}_{safe_original}"
    save_path = settings.upload_path / safe_name
    save_path.write_bytes(content)

    log.info("File saved", filename=safe_original, path=str(save_path))

    try:
        async with get_db() as db:
            result = await ingest_document(
                db=db,
                file_path=save_path,
                original_filename=safe_original,
            )
        return result
    except ValueError as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        log.error("Ingestion error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed. Check server logs.",
        )


@router.get(
    "/",
    response_model=DocumentList,
    summary="List all ingested documents",
)
async def list_documents(_: str = Depends(verify_api_key)):
    async with get_db() as db:
        docs = await db_ops.list_documents(db)
    return DocumentList(documents=docs, total=len(docs))


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get a single document by ID",
)
async def get_document(document_id: str, _: str = Depends(verify_api_key)):
    async with get_db() as db:
        doc = await db_ops.get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all its chunks/embeddings",
)
async def delete_document(document_id: str, _: str = Depends(verify_api_key)):
    async with get_db() as db:
        deleted = await delete_document_with_data(db, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
