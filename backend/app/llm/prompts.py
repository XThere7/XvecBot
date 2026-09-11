"""
llm/prompts.py
Prompt templates for the RAG pipeline.
All prompts are version-controlled here — changing a prompt is a code change,
not a scattered string edit across the codebase.
"""

SYSTEM_PROMPT = """You are a precise and helpful document assistant.
Your job is to answer the user's question based ONLY on the provided context passages.

Rules:
1. Answer ONLY from the context below. Do not use outside knowledge.
2. If the answer is not in the context, say: "I cannot find the answer in the provided document."
3. Reference page numbers naturally in your answer, e.g. "According to page 3, ..."
4. Be concise and direct. Quote the document when it strengthens the answer.
5. If multiple pages are relevant, synthesise them into a coherent answer.
"""

RAG_PROMPT_TEMPLATE = """{system}

--- DOCUMENT CONTEXT ---
{context}
--- END CONTEXT ---

User question: {question}

Answer:"""


def build_rag_prompt(query: str, context: str) -> str:
    """Format the full RAG prompt string."""
    return RAG_PROMPT_TEMPLATE.format(
        system=SYSTEM_PROMPT,
        context=context,
        question=query,
    )


# Grounding check prompt — used to verify answer is supported by context
GROUNDING_CHECK_PROMPT = """Given the following context and answer, determine if the answer
is fully supported by the context. Reply with only "SUPPORTED" or "NOT_SUPPORTED".

Context:
{context}

Answer:
{answer}"""
