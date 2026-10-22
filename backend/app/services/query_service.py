"""
services/query_service.py
Business logic for query processing.
Initialises the LLM, runs the LangGraph pipeline,
saves the conversation turn to DB, and returns the final response.
"""
from typing import Optional

import aiosqlite

from ..core.logging import get_logger
from ..graph.workflow import run_rag_pipeline
from ..llm.generator import build_generator
from ..models.query import QueryRequest, QueryResponse
from ..storage import sqlite as db_ops

log = get_logger(__name__)


async def _link_conversation_to_workspace(
    db: aiosqlite.Connection,
    conversation_id: str,
    citations: list,
) -> None:
    """
    Attach a legacy query transcript to the workspace it quotes.

    The legacy `/api/v1/query` API is global, so its conversations used to
    have no owner and survived a workspace delete. When the answer draws on a
    single workspace's documents we can attribute the transcript to it; a
    transcript that spans several tenants stays global (deleting it would
    destroy another tenant's data).
    """
    chunk_ids = [
        c.get("chunk_id")
        for c in (citations or [])
        if isinstance(c, dict) and c.get("chunk_id")
    ]
    if not chunk_ids:
        return
    placeholders = ",".join("?" * len(chunk_ids))
    async with db.execute(
        f"SELECT DISTINCT workspace_id FROM chunks WHERE id IN ({placeholders})",
        chunk_ids,
    ) as cur:
        rows = await cur.fetchall()
    workspaces: set[str] = set()
    for r in rows:
        # sqlite3.Row and asyncpg.Record both support r["col"] / r.keys()
        try:
            value = r["workspace_id"]
        except (KeyError, IndexError):
            continue
        if value:
            workspaces.add(value)
    if len(workspaces) != 1:
        return
    workspace_id = next(iter(workspaces))
    await db.execute(
        "UPDATE conversations SET workspace_id = ? WHERE id = ?",
        (workspace_id, conversation_id),
    )
    await db.commit()
    log.info(
        "Legacy conversation linked to workspace",
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )


async def process_query(
    db: aiosqlite.Connection,
    request: QueryRequest,
    workspace_id: Optional[str] = None,
) -> QueryResponse:
    """
    Entry point for the query flow.

    1. Ensure a conversation_id exists (create one if not provided).
    2. Save the user message to conversation history.
    3. Run the LangGraph RAG pipeline.
    4. Save the assistant answer + citations to conversation history.
    5. Return a QueryResponse.

    Args:
        db:       Active DB connection.
        request:  Validated QueryRequest from the API layer.

    Returns:
        QueryResponse with answer, citations, conversation_id, and metadata.
    """
    # Resolve conversation
    if request.conversation_id:
        conversation_id = request.conversation_id
    else:
        conversation_id = await db_ops.create_conversation(db)

    # Persist user message
    await db_ops.insert_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=request.question,
    )

    # Build LLM generator
    llm = build_generator()

    # Run the RAG pipeline
    log.info(
        "Running query pipeline",
        conversation_id=conversation_id,
        question=request.question[:80],
    )
    final_state = await run_rag_pipeline(
        query=request.question,
        conversation_id=conversation_id,
        db=db,
        llm_generator=llm,
        document_id=request.document_id,
        workspace_id=workspace_id,
    )

    # Persist assistant message
    await db_ops.insert_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=final_state["answer"],
        citations=final_state["citations"],
    )

    # Attribute the transcript to the workspace it quotes (single-tenant case)
    # so deleting that workspace also deletes the transcript.
    try:
        await _link_conversation_to_workspace(
            db, conversation_id, final_state.get("citations") or []
        )
    except Exception as exc:  # never fail a good answer over bookkeeping
        log.warning("Could not link legacy conversation to a workspace", error=str(exc))

    log.info(
        "Query complete",
        conversation_id=conversation_id,
        grounded=final_state["grounded"],
        citations=len(final_state["citations"]),
    )

    return QueryResponse(
        answer=final_state["answer"],
        citations=final_state["citations"],
        conversation_id=conversation_id,
        grounded=final_state["grounded"],
        retrieved_count=final_state["retrieved_count"],
    )
