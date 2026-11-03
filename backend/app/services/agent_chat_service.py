"""
services/agent_chat_service.py
Per-agent chat: loads the agent's own configuration, retrieves knowledge from
the agent's workspace, calls the LLM with the agent's model / temperature /
system_prompt, and persists the turn to the conversation history.

Retrieval mirrors workspace_query_service.py (hybrid search + rerank, scoped to
the workspace). The LLM is called through the OpenRouter generator, which
accepts a per-call system prompt, history, model and temperature.
"""
import asyncio
import time
from typing import Optional

import aiosqlite
from fastapi import HTTPException, status

from ..core.config import settings
from ..core.logging import get_logger
from ..ingestion.embedder import embed_query
from ..llm.generator import build_generator
from ..retrieval.hybrid_search import hybrid_search
from ..retrieval.reranker import rerank
from ..storage import sqlite as db_ops
from . import conversation_service, plan_service
from .workspace_query_service import (
    KNOWLEDGE_SAFETY,
    _build_sources,
    _source_metadata_for_chunks,
)

log = get_logger(__name__)


async def _load_agent(db: aiosqlite.Connection, agent_id: str) -> dict:
    """Fetch the agent row, or raise 404."""
    async with db.execute(
        "SELECT * FROM agents WHERE id = ?", (agent_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return dict(row)


async def _retrieve_knowledge(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    message: str,
) -> tuple[list, list[dict]]:
    """
    Retrieve and rerank chunks for the message.

    Workspace-wide documents are always included. Imported social media is
    included only for this agent (`chunks.agent_id = agent_id`), so another
    agent in the same workspace can never retrieve or cite it.
    """
    query_vector = await asyncio.to_thread(embed_query, message)
    hybrid_results = await hybrid_search(
        db=db,
        query=message,
        query_vector=query_vector,
        top_k=settings.retrieval_top_k,
        workspace_id=workspace_id,
        agent_id=agent_id,
    )

    chunk_ids = [r.chunk_id for r in hybrid_results]
    chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)
    chunk_map = {c.id: c for c in chunks}
    ordered_chunks = [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]

    reranked = rerank(
        query=message,
        chunks=ordered_chunks,
        top_k=settings.rerank_top_k,
    )
    reranked_chunks = [r.chunk for r in reranked]

    if not reranked_chunks:
        return [], []

    metadata = await _source_metadata_for_chunks(db, reranked_chunks)
    sources = _build_sources(reranked_chunks, metadata)
    return reranked_chunks, sources


def _format_context(chunks: list) -> str:
    """Format reranked chunks as the document context block."""
    return "\n\n---\n\n".join(f"[Page {c.page}]\n{c.text}" for c in chunks)


def _assemble_system_prompt(agent: dict, context: str) -> str:
    """
    Build the per-call system prompt:
      the agent's system_prompt
      + a language instruction (skipped for English / unset)
      + the retrieved knowledge context
    """
    parts = [agent["system_prompt"]]

    language = agent.get("language")
    if language and language != "English":
        parts.append(f"Always respond in {language}.")

    if context:
        parts.append(
            f"{KNOWLEDGE_SAFETY}\n\nRelevant knowledge:\n{context}"
        )

    return "\n\n".join(parts)


async def chat_with_agent(
    agent_id: str,
    conversation_id: Optional[str],
    message: str,
    db: aiosqlite.Connection,
    channel: str = "dashboard",
) -> dict:
    """
    Run one turn of an agent conversation.

    Returns:
        {
            "conversation_id": str,
            "answer": str,
            "sources": [{"filename": str, "chunk_index": int}, ...],
            "model_used": str,
        }

    ``channel`` is dashboard | widget | hosted | api and feeds the admin
    usage analytics. Recording is fire-and-forget — chat latency and
    reliability are unaffected if the usage write fails.
    """
    from . import admin_service

    started = time.perf_counter()
    try:
        return await _chat_with_agent_inner(
            agent_id, conversation_id, message, db, channel=channel,
            started=started,
        )
    except Exception as exc:
        # Error row with whatever meta we can recover cheaply.
        owner_id: str | None = None
        workspace_id: str | None = None
        model: str | None = None
        try:
            agent = await _load_agent(db, agent_id)
            workspace_id = agent["workspace_id"]
            model = agent["model"]
            workspace = await plan_service.get_workspace(db, workspace_id)
            owner_id = workspace["owner_id"] if workspace else None
        except Exception:
            pass
        admin_service.record_usage_event(
            user_id=owner_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            channel=channel,
            model=model,
            status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_code=type(exc).__name__,
        )
        raise


async def _chat_with_agent_inner(
    agent_id: str,
    conversation_id: Optional[str],
    message: str,
    db: aiosqlite.Connection,
    *,
    channel: str,
    started: float,
) -> dict:
    from . import admin_service

    # 1. Load agent config
    agent = await _load_agent(db, agent_id)
    workspace_id = agent["workspace_id"]

    # 1b. Account chat allowance. The counter is incremented here, before the
    # conversation is touched or the LLM is called, so a visitor cannot get a
    # free turn by racing the quota. AI-response analytics are still recorded
    # separately after a successful answer.
    workspace = await plan_service.get_workspace(db, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    await plan_service.assert_can_chat(db, workspace)

    # 2. Resolve or create the conversation
    is_new = conversation_id is None
    if is_new:
        conversation = await conversation_service.create_conversation(
            db, agent_id, workspace_id=workspace_id
        )
        conversation_id = conversation["id"]
    else:
        conversation = await conversation_service.get_conversation(db, conversation_id)
        if conversation is None or conversation["agent_id"] != agent_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    # 3. Store the user message
    await conversation_service.add_message(
        db, conversation_id, role="user", content=message
    )

    # 4. Build history for the LLM — exclude the just-stored user message so it
    #    is not duplicated when the LLM call appends it.
    history = await conversation_service.build_history_for_llm(db, conversation_id)
    history = history[:-1] if history else history

    # 5. Retrieve relevant knowledge from the agent's workspace
    reranked_chunks, sources = await _retrieve_knowledge(
        db, workspace_id, agent_id, message
    )
    context = _format_context(reranked_chunks)

    # 6. Assemble the system prompt
    system_prompt = _assemble_system_prompt(agent, context)

    # 7. Call the LLM with the agent's own model and temperature
    llm = build_generator()
    answer = await llm.generate(
        query=message,
        context=context,
        system_prompt=system_prompt,
        history=history,
        model=agent["model"],
        temperature=agent["temperature"],
    )
    model_used = llm.last_model_used

    # 8. Store the assistant response
    await conversation_service.add_message(
        db, conversation_id, role="assistant", content=answer, sources=sources
    )

    # 8b. Analytics ledger: only successful answers are counted here. The
    # monthly chat-message allowance was already incremented before generation,
    # so a failed model call still consumes the message it attempted.
    await plan_service.record_ai_response(db, workspace_id)

    # 9. Auto-title if this was a new conversation
    if is_new:
        await conversation_service.auto_title_conversation(
            db, conversation_id, message
        )

    log.info(
        "Agent chat complete",
        agent_id=agent_id,
        conversation_id=conversation_id,
        model_used=model_used,
        sources=len(sources),
    )

    # 10. Usage analytics (fire-and-forget; never affects the response).
    admin_service.record_usage_event(
        user_id=workspace["owner_id"],
        workspace_id=workspace_id,
        agent_id=agent_id,
        channel=channel,
        model=model_used or agent["model"],
        status="ok",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

    # 11. Return the response
    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "sources": sources,
        "model_used": model_used,
    }
