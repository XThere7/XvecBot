"""
storage/sqlite.py
All relational SQLite CRUD operations: documents, chunks, conversations, messages.
This is the only layer that touches SQL directly — services call these functions.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from ..models.chunk import Chunk
from ..models.document import DocumentRead
from ..models.query import Citation, ConversationMessage
from ..core.logging import get_logger

log = get_logger(__name__)


# ── Documents ─────────────────────────────────────────────────────────────────

async def insert_document(
    db: aiosqlite.Connection,
    *,
    filename: str,
    total_pages: int,
    file_size: int,
) -> str:
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO documents (id, filename, upload_date, total_pages, file_size, status)
           VALUES (?, ?, ?, ?, ?, 'processing')""",
        (doc_id, filename, now, total_pages, file_size),
    )
    await db.commit()
    log.info("Document inserted", doc_id=doc_id, filename=filename)
    return doc_id


async def update_document_status(
    db: aiosqlite.Connection, doc_id: str, status: str
) -> None:
    await db.execute(
        "UPDATE documents SET status = ? WHERE id = ?", (status, doc_id)
    )
    await db.commit()


async def get_document(
    db: aiosqlite.Connection, doc_id: str
) -> Optional[DocumentRead]:
    async with db.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return DocumentRead(
        id=row["id"],
        filename=row["filename"],
        upload_date=row["upload_date"],
        total_pages=row["total_pages"],
        file_size=row["file_size"],
        status=row["status"],
    )


async def list_documents(db: aiosqlite.Connection) -> list[DocumentRead]:
    async with db.execute(
        "SELECT * FROM documents ORDER BY upload_date DESC"
    ) as cur:
        rows = await cur.fetchall()
    return [
        DocumentRead(
            id=r["id"],
            filename=r["filename"],
            upload_date=r["upload_date"],
            total_pages=r["total_pages"],
            file_size=r["file_size"],
            status=r["status"],
        )
        for r in rows
    ]


async def delete_document(db: aiosqlite.Connection, doc_id: str) -> bool:
    async with db.execute(
        "SELECT id FROM documents WHERE id = ?", (doc_id,)
    ) as cur:
        if await cur.fetchone() is None:
            return False
    await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await db.commit()
    return True


# ── Chunks ────────────────────────────────────────────────────────────────────

async def insert_chunk(
    db: aiosqlite.Connection,
    *,
    document_id: str,
    page: int,
    chunk_index: int,
    text: str,
) -> str:
    chunk_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO chunks (id, document_id, page, chunk_index, text)
           VALUES (?, ?, ?, ?, ?)""",
        (chunk_id, document_id, page, chunk_index, text),
    )
    return chunk_id


async def get_chunks_by_ids(
    db: aiosqlite.Connection, chunk_ids: list[str]
) -> list[Chunk]:
    placeholders = ",".join("?" * len(chunk_ids))
    async with db.execute(
        f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids
    ) as cur:
        rows = await cur.fetchall()
    return [
        Chunk(
            id=r["id"],
            document_id=r["document_id"],
            page=r["page"],
            chunk_index=r["chunk_index"],
            text=r["text"],
        )
        for r in rows
    ]


async def get_all_chunks(
    db: aiosqlite.Connection, document_id: Optional[str] = None
) -> list[Chunk]:
    if document_id:
        async with db.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY page, chunk_index",
            (document_id,),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM chunks ORDER BY document_id, page, chunk_index"
        ) as cur:
            rows = await cur.fetchall()
    return [
        Chunk(
            id=r["id"],
            document_id=r["document_id"],
            page=r["page"],
            chunk_index=r["chunk_index"],
            text=r["text"],
        )
        for r in rows
    ]


async def count_chunks(db: aiosqlite.Connection, document_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (document_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


# ── Conversations ─────────────────────────────────────────────────────────────

async def create_conversation(db: aiosqlite.Connection) -> str:
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
        (conv_id, now),
    )
    await db.commit()
    return conv_id


async def insert_message(
    db: aiosqlite.Connection,
    *,
    conversation_id: str,
    role: str,
    content: str,
    citations: Optional[list[Citation]] = None,
) -> str:
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    citations_json = (
        json.dumps([c.model_dump() for c in citations]) if citations else None
    )
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, citations, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (msg_id, conversation_id, role, content, citations_json, now),
    )
    await db.commit()
    return msg_id


async def get_conversation_messages(
    db: aiosqlite.Connection, conversation_id: str
) -> list[ConversationMessage]:
    async with db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
        (conversation_id,),
    ) as cur:
        rows = await cur.fetchall()
    messages = []
    for r in rows:
        citations = []
        if r["citations"]:
            raw = json.loads(r["citations"])
            citations = [Citation(**c) for c in raw]
        messages.append(
            ConversationMessage(role=r["role"], content=r["content"], citations=citations)
        )
    return messages
