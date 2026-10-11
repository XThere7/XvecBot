"""
api/documents.py
Workspace-scoped document upload/list/delete plus training endpoints.
Training pipeline itself lives in services/workspace_training_service.py.

Two upload flows (Phase 2):
  - Legacy direct upload (POST /{ws}/documents): bytes via FastAPI to local
    disk. Unchanged — still the default when object storage is unconfigured.
  - Presigned upload (upload-url -> PUT to R2/S3 -> complete-upload): browser
    talks to storage directly. Requires S3_BUCKET (+ R2 endpoint/creds).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..services.workspace_query_service import query_workspace
from ..services.workspace_training_service import train_workspace_document
from ..storage import vector_store
from ..storage.object_store import (
    build_object_key,
    content_type_for,
    get_storage,
)
from .deps import get_current_user
from .workspaces import _get_owned_workspace

log = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}


@router.post(
    "/{workspace_id}/documents",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document into a workspace",
)
async def upload_document(
    workspace_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        original = Path(file.filename or "").name  # strip any path components
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{ext or 'none'}'. Allowed: .pdf, .txt, .docx",
            )

        content = await file.read()

        dest_dir = settings.workspace_upload_path / workspace_id
        os.makedirs(dest_dir, exist_ok=True)

        doc_id = str(uuid.uuid4())
        save_path = dest_dir / f"{doc_id}_{original}"
        save_path.write_bytes(content)

        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT INTO workspace_documents
                   (id, workspace_id, filename, file_path, file_type,
                    size_bytes, status, chunk_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'uploaded', 0, ?)""",
                (
                    doc_id,
                    workspace_id,
                    original,
                    str(save_path),
                    ext.lstrip("."),
                    len(content),
                    now,
                ),
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM workspace_documents WHERE id = ?", (doc_id,)
            ) as cur:
                row = await cur.fetchone()
        except Exception:
            save_path.unlink(missing_ok=True)
            raise

    log.info(
        "Workspace document uploaded",
        doc_id=doc_id,
        workspace_id=workspace_id,
        filename=original,
        size=len(content),
    )
    return dict(row)


class UploadUrlRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=1)


@router.post(
    "/{workspace_id}/documents/upload-url",
    status_code=status.HTTP_201_CREATED,
    summary="Mint a presigned PUT URL for direct browser-to-storage upload",
)
async def create_upload_url(
    workspace_id: str,
    payload: UploadUrlRequest,
    user: dict = Depends(get_current_user),
):
    """Presigned flow step 1: reserve the document row, hand out a PUT URL.

    Requires object storage (S3_BUCKET). Legacy direct upload is unaffected.
    Next: browser PUTs bytes to `url`, then calls complete-upload, then /train.
    """
    if not settings.use_s3_storage:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Object storage is not configured (S3_BUCKET). Use direct upload.",
        )
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        original = Path(payload.filename or "").name
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{ext or 'none'}'. Allowed: .pdf, .txt, .docx",
            )
        if (
            payload.size_bytes is not None
            and payload.size_bytes > settings.max_upload_bytes
        ):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large (max {settings.max_upload_bytes} bytes)",
            )

        content_type = payload.content_type or content_type_for(original)
        doc_id = str(uuid.uuid4())
        object_key = build_object_key(
            workspace_id, doc_id, original, settings.s3_prefix
        )
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO workspace_documents
               (id, workspace_id, filename, file_path, file_type,
                size_bytes, status, chunk_count, created_at,
                object_key, content_type, etag)
               VALUES (?, ?, ?, '', ?, 0, 'pending_upload', 0, ?, ?, ?, NULL)""",
            (
                doc_id,
                workspace_id,
                original,
                ext.lstrip("."),
                now,
                object_key,
                content_type,
            ),
        )
        await db.commit()

        storage = get_storage()
        try:
            put_url = await asyncio.to_thread(
                storage.presigned_put,
                object_key,
                content_type,
                settings.presigned_put_expires,
            )
        except Exception as exc:
            log.error("Presigned PUT failed", error=str(exc), doc_id=doc_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not mint upload URL. Check storage configuration.",
            )

    log.info(
        "Upload URL minted",
        doc_id=doc_id,
        workspace_id=workspace_id,
        filename=original,
    )
    return {
        "doc_id": doc_id,
        "method": "presigned-put",
        "url": put_url,
        "object_key": object_key,
        "content_type": content_type,
        "expires_in": settings.presigned_put_expires,
    }


@router.post(
    "/{workspace_id}/documents/{doc_id}/complete-upload",
    summary="Verify a presigned upload landed, mark the document uploaded",
)
async def complete_upload(
    workspace_id: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """Presigned flow step 2: HEAD the object, enforce size/type, flip status.

    Next: POST .../train (unchanged) reads bytes from object storage.
    """
    if not settings.use_s3_storage:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Object storage is not configured (S3_BUCKET).",
        )
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        doc = dict(row)
        if not doc.get("object_key"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document was not created via upload-url.",
            )
        if doc.get("status") not in ("pending_upload", "uploaded"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot complete upload from status '{doc.get('status')}'.",
            )

        storage = get_storage()
        head = await asyncio.to_thread(storage.head_object, doc["object_key"])
        if head is None or head.size_bytes <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Object not found in storage yet. PUT the bytes first, then retry.",
            )
        if head.size_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large (max {settings.max_upload_bytes} bytes)",
            )

        await db.execute(
            """UPDATE workspace_documents
               SET status = 'uploaded', size_bytes = ?, etag = ?
               WHERE id = ?""",
            (head.size_bytes, head.etag, doc_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ?", (doc_id,)
        ) as cur:
            updated = await cur.fetchone()

    log.info(
        "Upload completed",
        doc_id=doc_id,
        workspace_id=workspace_id,
        size=head.size_bytes,
    )
    return dict(updated)


@router.get(
    "/{workspace_id}/documents/{doc_id}/download-url",
    summary="Mint a presigned GET URL for downloading the stored object",
)
async def create_download_url(
    workspace_id: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    if not settings.use_s3_storage:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Object storage is not configured (S3_BUCKET). Files are on local disk.",
        )
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        doc = dict(row)
        if not doc.get("object_key"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no stored object (legacy local upload).",
            )
        storage = get_storage()
        try:
            get_url = await asyncio.to_thread(
                storage.presigned_get,
                doc["object_key"],
                settings.presigned_get_expires,
            )
        except Exception as exc:
            log.error("Presigned GET failed", error=str(exc), doc_id=doc_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not mint download URL. Check storage configuration.",
            )
    return {
        "method": "presigned-get",
        "url": get_url,
        "expires_in": settings.presigned_get_expires,
        "filename": doc.get("filename"),
        "size_bytes": doc.get("size_bytes"),
    }


@router.get(
    "/{workspace_id}/documents",
    summary="List documents in a workspace",
)
async def list_documents(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        async with db.execute(
            "SELECT * FROM workspace_documents WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.delete(
    "/{workspace_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace document",
)
async def delete_document(
    workspace_id: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # 1. remove file from disk (ignore if already gone)
        try:
            os.remove(row["file_path"])
        except OSError:
            pass

        # 1b. remove stored object (presigned-flow rows; best-effort)
        object_key = dict(row).get("object_key")
        if object_key and settings.use_s3_storage:
            try:
                await asyncio.to_thread(get_storage().delete_object, object_key)
            except Exception as exc:
                log.warning(
                    "Object delete failed",
                    doc_id=doc_id,
                    error=str(exc),
                )

        # 2. remove vector embeddings for this document
        await vector_store.delete_embeddings_for_document(db, doc_id)

        # 3. remove chunk rows (text content) for this document
        await db.execute(
            "DELETE FROM chunks WHERE document_id = ?", (doc_id,)
        )

        # 4. remove the workspace_documents row
        await db.execute(
            "DELETE FROM workspace_documents WHERE id = ?", (doc_id,)
        )
        await db.commit()

    log.info(
        "Workspace document deleted",
        doc_id=doc_id,
        workspace_id=workspace_id,
        filename=row["filename"],
    )


@router.post(
    "/{workspace_id}/documents/{doc_id}/train",
    summary="Start training a workspace document",
)
async def train_document(
    workspace_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        current_status = row["status"]
        if current_status == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already processing. Wait for it to finish.",
            )
        if current_status == "ready":
            return {
                "status": "ready",
                "message": "Already trained. Delete and re-upload to retrain.",
            }

        # Claim the document before scheduling so a concurrent request hits 409.
        await db.execute(
            "UPDATE workspace_documents SET status = 'processing' WHERE id = ?",
            (doc_id,),
        )
        await db.commit()

    background_tasks.add_task(train_workspace_document, doc_id)

    log.info("Training scheduled", doc_id=doc_id, workspace_id=workspace_id)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "processing",
            "message": "Training started. Use /status to poll.",
        },
    )


@router.get(
    "/{workspace_id}/documents/{doc_id}/status",
    summary="Get training status for a workspace document",
)
async def document_status(
    workspace_id: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        async with db.execute(
            "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

    return {
        "doc_id": row["id"],
        "filename": row["filename"],
        "status": row["status"],
        "chunk_count": row["chunk_count"],
    }


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_history: list = Field(default_factory=list)


@router.post(
    "/{workspace_id}/chat",
    summary="Chat with this workspace's documents",
)
async def chat(
    workspace_id: str,
    payload: ChatRequest,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        workspace = await _get_owned_workspace(db, workspace_id, user["id"])
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        try:
            result = await query_workspace(
                workspace_id=workspace_id,
                message=payload.message,
                conversation_history=payload.conversation_history,
                db=db,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        except Exception as exc:
            log.error("Workspace chat error", error=str(exc), workspace_id=workspace_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat failed. Check server logs.",
            )

    return result
