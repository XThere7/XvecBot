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
