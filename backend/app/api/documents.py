"""
api/documents.py
Workspace-scoped document upload/list/delete.
Training (ingestion + embedding) is NOT here — it comes in the next task.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..storage import vector_store
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

        # 2. remove vector chunks for this document
        await vector_store.delete_embeddings_for_document(db, doc_id)

        # 3. remove the workspace_documents row
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
