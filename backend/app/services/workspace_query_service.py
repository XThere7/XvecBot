"""
services/workspace_query_service.py
Per-workspace chat: retrieval is scoped to one workspace, the workspace's
system_prompt and the conversation history are passed to the LLM.

Reuses the Phase 1 retrieval stack (hybrid_search -> rerank) and the existing
LLMGenerator interface. The workspace system_prompt is prepended to the context,
matching the pattern used by the OpenRouter generator.
"""
import asyncio
from typing import Any, Optional

import aiosqlite

from ..core.config import settings
from ..core.logging import get_logger
from ..ingestion.embedder import embed_query
from ..llm.generator import build_generator
from ..models.chunk import Chunk
from ..retrieval.hybrid_search import hybrid_search
from ..retrieval.reranker import rerank
from ..storage import sqlite as db_ops

log = get_logger(__name__)

NOT_FOUND_ERROR = "Workspace not found"
NO_CONTEXT_ERROR = (
    "I could not find relevant information in this workspace's documents "
    "to answer your question."
)


async def _get_workspace(db: aiosqlite.Connection, workspace_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row is not None else None


async def _filenames_for_chunks(
    db: aiosqlite.Connection,
    chunks: list[Chunk],
) -> dict[str, str]:
    """Map chunk_id -> source filename (workspace doc first, legacy doc fallback)."""
    if not chunks:
        return {}
    placeholders = ",".join("?" * len(chunks))
    async with db.execute(
        f"""SELECT c.id AS chunk_id,
                   COALESCE(wd.filename, d.filename) AS filename
            FROM chunks c
            LEFT JOIN workspace_documents wd ON wd.id = c.doc_id
            LEFT JOIN documents d ON d.id = c.document_id
            WHERE c.id IN ({placeholders})""",
        [c.id for c in chunks],
    ) as cur:
        rows = await cur.fetchall()
    return {r["chunk_id"]: r["filename"] for r in rows if r["filename"]}


def _format_history(history: list) -> str:
    """Render prior turns so the LLM can follow the conversation."""
    lines = []
    for turn in history:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_sources(chunks: list[Chunk], filenames: dict[str, str]) -> list[dict[str, Any]]:
    """One source entry per retrieved chunk, de-duplicated per (file, chunk_index)."""
    sources: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for chunk in chunks:
        filename = filenames.get(chunk.id, "unknown")
        key = (filename, chunk.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        sources.append({"filename": filename, "chunk_index": chunk.chunk_index})
    return sources


async def query_workspace(
    workspace_id: str,
    message: str,
    conversation_history: list,
    db: aiosqlite.Connection,
) -> dict:
    """
    Answer a question using only this workspace's trained documents.

    Returns:
        {
            "answer": str,
            "sources": [{"filename": str, "chunk_index": int}, ...],
            "conversation_history": [ ...prior turns + user + assistant ],
        }
    """
    workspace = await _get_workspace(db, workspace_id)
    if workspace is None:
        raise ValueError(NOT_FOUND_ERROR)

    system_prompt = workspace["system_prompt"]
    history = list(conversation_history or [])

    # 1. Retrieve — scoped to this workspace only
    query_vector = await asyncio.to_thread(embed_query, message)
    hybrid_results = await hybrid_search(
        db=db,
        query=message,
        query_vector=query_vector,
        top_k=settings.retrieval_top_k,
        workspace_id=workspace_id,
    )

    chunk_ids = [r.chunk_id for r in hybrid_results]
    chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)
    chunk_map = {c.id: c for c in chunks}
    ordered_chunks = [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]

    # 2. Rerank
    reranked = rerank(
        query=message,
        chunks=ordered_chunks,
        top_k=settings.rerank_top_k,
    )
    reranked_chunks = [r.chunk for r in reranked]

    if not reranked_chunks:
        log.info(
            "Workspace query: no context found",
            workspace_id=workspace_id,
        )
        answer = NO_CONTEXT_ERROR
        sources: list[dict[str, Any]] = []
    else:
        filenames = await _filenames_for_chunks(db, reranked_chunks)
        sources = _build_sources(reranked_chunks, filenames)

        # 3. Build context, prepending the workspace system_prompt
        context_parts = [f"[Page {c.page}]\n{c.text}" for c in reranked_chunks]
        context = "\n\n---\n\n".join(context_parts)
        context = f"{system_prompt}\n\n--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---"

        history_block = _format_history(history)
        augmented_query = (
            f"--- CONVERSATION SO FAR ---\n{history_block}\n--- END ---\n\n"
            if history_block
            else ""
        ) + message

        llm = build_generator()
        answer = await llm.generate(query=augmented_query, context=context)

    # 4. Append this turn to the returned history
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer})

    log.info(
        "Workspace query complete",
        workspace_id=workspace_id,
        retrieved=len(reranked_chunks),
        sources=len(sources),
    )

    return {
        "answer": answer,
        "sources": sources,
        "conversation_history": history,
    }
