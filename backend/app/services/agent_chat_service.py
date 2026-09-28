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
from . import conversation_service
from .workspace_query_service import _build_sources, _filenames_for_chunks

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
    message: str,
) -> tuple[list, list[dict]]:
    """
    Retrieve and rerank chunks for the message, scoped to the workspace.

    Same approach as workspace_query_service: embed -> hybrid search -> rerank.
    Returns (reranked_chunks, sources). Both empty when the workspace has no
    trained documents — the caller proceeds without context.
    """
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

    reranked = rerank(
        query=message,
        chunks=ordered_chunks,
        top_k=settings.rerank_top_k,
    )
    reranked_chunks = [r.chunk for r in reranked]

    if not reranked_chunks:
        return [], []

    filenames = await _filenames_for_chunks(db, reranked_chunks)
    sources = _build_sources(reranked_chunks, filenames)
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
        parts.append(f"Relevant knowledge:\n{context}")

    return "\n\n".join(parts)


async def chat_with_agent(
    agent_id: str,
    conversation_id: Optional[str],
    message: str,
    db: aiosqlite.Connection,
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
    """
    # 1. Load agent config
    agent = await _load_agent(db, agent_id)
    workspace_id = agent["workspace_id"]

    # 2. Resolve or create the conversation
    is_new = conversation_id is None
    if is_new:
        conversation = await conversation_service.create_conversation(db, agent_id)
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
    reranked_chunks, sources = await _retrieve_knowledge(db, workspace_id, message)
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

    # 10. Return the response
    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "sources": sources,
        "model_used": model_used,
    }
