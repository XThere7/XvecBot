"""
graph/nodes.py
LangGraph node functions — each node takes the current RAGState,
performs one step of the pipeline, and returns a dict of state updates.
LangGraph merges the returned dict into the state before calling the next node.

Node order:
  retrieve_node -> rerank_node -> grounding_node -> generate_node -> citation_node
"""
from typing import Optional
import aiosqlite

from ..core.config import settings
from ..core.logging import get_logger
from ..ingestion.embedder import embed_query
from ..models.chunk import Chunk
from ..models.query import Citation
from ..retrieval.hybrid_search import hybrid_search
from ..retrieval.reranker import rerank
from ..storage import sqlite as db_ops
from .state import RAGState

log = get_logger(__name__)


# ── Node 1: Retrieve ──────────────────────────────────────────────────────────

async def retrieve_node(state: RAGState, db: aiosqlite.Connection) -> dict:
    """
    Embed the query and run hybrid search (BM25 + vector + RRF).
    Writes: query_vector, retrieved_chunk_ids, retrieved_chunks, retrieved_count.
    """
    log.info("retrieve_node: starting", query=state["query"][:80])

    query_vector = embed_query(state["query"])

    hybrid_results = await hybrid_search(
        db=db,
        query=state["query"],
        query_vector=query_vector,
        top_k=settings.retrieval_top_k,
        document_id=state.get("document_id"),
        workspace_id=state.get("workspace_id"),
    )

    chunk_ids = [r.chunk_id for r in hybrid_results]
    chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)

    # Preserve the RRF rank order from hybrid search
    chunk_map = {c.id: c for c in chunks}
    ordered_chunks = [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]

    log.info("retrieve_node: complete", retrieved=len(ordered_chunks))
    return {
        "query_vector": query_vector,
        "retrieved_chunk_ids": chunk_ids,
        "retrieved_chunks": ordered_chunks,
        "retrieved_count": len(ordered_chunks),
    }


# ── Node 2: Rerank ────────────────────────────────────────────────────────────

def rerank_node(state: RAGState) -> dict:
    """
    Apply cross-encoder reranking to the retrieved candidates.
    Writes: reranked_chunks.
    """
    log.info("rerank_node: starting", candidates=len(state["retrieved_chunks"]))

    rerank_results = rerank(
        query=state["query"],
        chunks=state["retrieved_chunks"],
        top_k=settings.rerank_top_k,
    )

    reranked = [r.chunk for r in rerank_results]
    log.info("rerank_node: complete", reranked=len(reranked))
    return {"reranked_chunks": reranked}


# ── Node 3: Grounding ─────────────────────────────────────────────────────────

def grounding_node(state: RAGState) -> dict:
    """
    Verify that the retrieved chunks contain enough content to answer.
    If none of the top chunks have sufficient text, flag as not grounded —
    the generate_node will produce a refusal instead of a hallucinated answer.
    Writes: grounded, grounding_message.
    """
    log.info("grounding_node: starting")

    chunks = state["reranked_chunks"]
    if not chunks:
        log.warning("grounding_node: no chunks — not grounded")
        return {
            "grounded": False,
            "grounding_message": (
                "I could not find relevant information in the uploaded document(s) "
                "to answer your question."
            ),
        }

    # Heuristic: at least one chunk must have meaningful content (>50 chars)
    meaningful = [c for c in chunks if len(c.text.strip()) > 50]
    if not meaningful:
        log.warning("grounding_node: chunks too short — not grounded")
        return {
            "grounded": False,
            "grounding_message": (
                "The retrieved passages do not contain sufficient detail "
                "to answer your question accurately."
            ),
        }

    log.info("grounding_node: grounded", meaningful_chunks=len(meaningful))
    return {"grounded": True, "grounding_message": None}


# ── Node 4: Generate ──────────────────────────────────────────────────────────

async def generate_node(state: RAGState, llm_generator) -> dict:
    """
    Build the context string and call the LLM.
    If not grounded, returns the grounding_message as the answer without LLM call.
    Writes: context, answer.
    """
    if not state.get("grounded", False):
        log.info("generate_node: skipping LLM — not grounded")
        return {
            "context": "",
            "answer": state.get("grounding_message", "I cannot answer from the provided documents."),
        }

    log.info("generate_node: building context and generating answer")

    # Build context with page-prefixed chunks
    context_parts = []
    for chunk in state["reranked_chunks"]:
        context_parts.append(f"[Page {chunk.page}]\n{chunk.text}")
    context = "\n\n---\n\n".join(context_parts)

    answer = await llm_generator.generate(
        query=state["query"],
        context=context,
    )

    log.info("generate_node: complete", answer_length=len(answer))
    return {"context": context, "answer": answer}


# ── Node 5: Citations ─────────────────────────────────────────────────────────

def citation_node(state: RAGState) -> dict:
    """
    Extract page-level citations from the reranked chunks used in generation.
    De-duplicates pages and preserves rank order.
    Writes: citations.
    """
    log.info("citation_node: extracting citations")

    if not state.get("grounded", False):
        return {"citations": []}

    seen_pages: set[int] = set()
    citations: list[Citation] = []

    for chunk in state["reranked_chunks"]:
        if chunk.page not in seen_pages:
            seen_pages.add(chunk.page)
            citations.append(
                Citation(
                    page=chunk.page,
                    chunk_id=chunk.id,
                    text_preview=chunk.text[:200],
                )
            )

    log.info("citation_node: complete", citations=len(citations))
    return {"citations": citations}
