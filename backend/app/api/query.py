"""
api/query.py
Query and conversation endpoints.
Thin routing layer — all logic lives in query_service.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
import json

from ..core.database import get_db
from ..core.logging import get_logger
from ..models.query import (
    ConversationHistory,
    QueryRequest,
    QueryResponse,
)
from ..services.query_service import process_query
from ..storage import sqlite as db_ops
from ..llm.generator import build_generator
from ..graph.workflow import run_rag_pipeline
from ..ingestion.embedder import embed_query
from .deps import verify_api_key

log = get_logger(__name__)
router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "/",
    response_model=QueryResponse,
    summary="Ask a question about uploaded documents",
)
async def ask(
    request: QueryRequest,
    _: str = Depends(verify_api_key),
):
    """
    Run the full RAG pipeline:
      Retrieve -> Rerank -> Ground -> Generate -> Citations

    Returns the answer with page-level citations and conversation_id.
    Include the returned conversation_id in subsequent requests to maintain
    chat history.
    """
    try:
        async with get_db() as db:
            response = await process_query(db=db, request=request)
        return response
    except Exception as exc:
        log.error("Query processing error", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Query processing failed. Check server logs.",
        )


@router.post(
    "/stream",
    summary="Stream a RAG answer token by token (SSE)",
)
async def ask_stream(
    request: QueryRequest,
    _: str = Depends(verify_api_key),
):
    """
    Server-Sent Events streaming endpoint.
    Each event is a JSON object: {"token": "...", "done": false}
    The final event includes: {"done": true, "citations": [...], "conversation_id": "..."}

    Frontend consumes with EventSource or fetch + ReadableStream.
    """
    async def event_generator():
        try:
            async with get_db() as db:
                # Resolve / create conversation
                if request.conversation_id:
                    conversation_id = request.conversation_id
                else:
                    conversation_id = await db_ops.create_conversation(db)

                await db_ops.insert_message(
                    db,
                    conversation_id=conversation_id,
                    role="user",
                    content=request.question,
                )

                # Build context via retrieval pipeline (non-streaming part)
                from ..retrieval.hybrid_search import hybrid_search
                from ..retrieval.reranker import rerank
                from ..graph.nodes import grounding_node
                from ..models.query import Citation

                query_vector = embed_query(request.question)
                hybrid_results = await hybrid_search(
                    db=db,
                    query=request.question,
                    query_vector=query_vector,
                    document_id=request.document_id,
                )
                chunk_ids = [r.chunk_id for r in hybrid_results]
                chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)

                reranked = rerank(query=request.question, chunks=chunks)
                reranked_chunks = [r.chunk for r in reranked]

                # Grounding check
                state = {
                    "reranked_chunks": reranked_chunks,
                    "grounded": False,
                    "grounding_message": None,
                }
                grounding_result = grounding_node(state)
                grounded = grounding_result["grounded"]

                if not grounded:
                    msg = grounding_result.get("grounding_message", "Cannot answer from documents.")
                    yield f"data: {json.dumps({'token': msg, 'done': False})}\n\n"
                    yield f"data: {json.dumps({'done': True, 'citations': [], 'conversation_id': conversation_id, 'grounded': False})}\n\n"
                    return

                # Build context
                context_parts = [f"[Page {c.page}]\n{c.text}" for c in reranked_chunks]
                context = "\n\n---\n\n".join(context_parts)

                # Stream LLM tokens
                llm = build_generator()
                full_answer = ""
                async for token in llm.stream(query=request.question, context=context):
                    full_answer += token
                    yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

                # Build citations
                seen_pages = set()
                citations = []
                for chunk in reranked_chunks:
                    if chunk.page not in seen_pages:
                        seen_pages.add(chunk.page)
                        citations.append(Citation(
                            page=chunk.page,
                            chunk_id=chunk.id,
                            text_preview=chunk.text[:200],
                        ))

                # Save to conversation history
                await db_ops.insert_message(
                    db,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_answer,
                    citations=citations,
                )

                yield f"data: {json.dumps({'done': True, 'citations': [c.model_dump() for c in citations], 'conversation_id': conversation_id, 'grounded': True})}\n\n"

        except Exception as exc:
            log.error("Stream error", error=str(exc))
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationHistory,
    summary="Retrieve full conversation history",
)
async def get_conversation(
    conversation_id: str,
    _: str = Depends(verify_api_key),
):
    async with get_db() as db:
        messages = await db_ops.get_conversation_messages(db, conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationHistory(
        conversation_id=conversation_id,
        messages=messages,
    )
