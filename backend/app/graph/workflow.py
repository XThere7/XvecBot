"""
graph/workflow.py
Assembles the LangGraph StateGraph for the RAG pipeline.

Graph topology:
  START -> retrieve -> rerank -> grounding -> generate -> citations -> END

The grounding node uses a conditional edge:
  - If grounded=True  -> generate
  - If grounded=False -> generate (generate_node handles the refusal path)

Both paths merge at generate to keep the graph linear and readable.
"""
from typing import Optional

import aiosqlite
from langgraph.graph import END, START, StateGraph

from ..core.logging import get_logger
from ..llm.generator import LLMGenerator
from .nodes import (
    citation_node,
    generate_node,
    grounding_node,
    rerank_node,
    retrieve_node,
)
from .state import RAGState

log = get_logger(__name__)


def build_rag_graph(
    db: aiosqlite.Connection,
    llm_generator: LLMGenerator,
) -> StateGraph:
    """
    Build and compile the RAG StateGraph.
    The db connection and llm_generator are injected so nodes can be
    unit-tested with mocks without touching the DB or LLM.

    Returns a compiled LangGraph that can be invoked with:
        result = await graph.ainvoke(initial_state)
    """
    # Wrap nodes that need injected dependencies
    async def _retrieve(state: RAGState) -> dict:
        return await retrieve_node(state, db)

    def _rerank(state: RAGState) -> dict:
        return rerank_node(state)

    def _grounding(state: RAGState) -> dict:
        return grounding_node(state)

    async def _generate(state: RAGState) -> dict:
        return await generate_node(state, llm_generator)

    def _citations(state: RAGState) -> dict:
        return citation_node(state)

    # Build the graph
    graph = StateGraph(RAGState)

    graph.add_node("retrieve",  _retrieve)
    graph.add_node("rerank",    _rerank)
    graph.add_node("grounding", _grounding)
    graph.add_node("generate",  _generate)
    graph.add_node("citations", _citations)

    # Wire the edges
    graph.add_edge(START,       "retrieve")
    graph.add_edge("retrieve",  "rerank")
    graph.add_edge("rerank",    "grounding")
    graph.add_edge("grounding", "generate")
    graph.add_edge("generate",  "citations")
    graph.add_edge("citations", END)

    compiled = graph.compile()
    log.info("RAG graph compiled")
    return compiled


async def run_rag_pipeline(
    query: str,
    conversation_id: str,
    db: aiosqlite.Connection,
    llm_generator: LLMGenerator,
    document_id: Optional[str] = None,
) -> RAGState:
    """
    Convenience wrapper: build the graph, run it, return the final state.
    This is the single entry point called by query_service.
    """
    graph = build_rag_graph(db, llm_generator)

    initial_state: RAGState = {
        "query": query,
        "conversation_id": conversation_id,
        "document_id": document_id,
        "query_vector": None,
        "retrieved_chunk_ids": [],
        "retrieved_chunks": [],
        "retrieved_count": 0,
        "reranked_chunks": [],
        "grounded": False,
        "grounding_message": None,
        "context": "",
        "answer": "",
        "citations": [],
    }

    log.info("Running RAG pipeline", query=query[:80], conversation_id=conversation_id)
    final_state: RAGState = await graph.ainvoke(initial_state)
    log.info(
        "RAG pipeline complete",
        grounded=final_state["grounded"],
        citations=len(final_state["citations"]),
        answer_length=len(final_state["answer"]),
    )
    return final_state
