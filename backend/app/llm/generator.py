"""
llm/generator.py
LLM generation wrapper. Single provider: OpenRouter (cloud chat-completions).

  OPENROUTER_API_KEY=...   (required — get one at https://openrouter.ai/keys)
  OPENROUTER_MODEL=inclusionai/ling-3.0-flash-fin:free
  OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

Import build_generator() in services/query_service.py — never import backends
directly. build_generator() returns an OpenRouterGenerator unconditionally.
MockGenerator below is a test-only stub (not wired to the factory).
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from ..core.logging import get_logger

log = get_logger(__name__)


class LLMGenerator(ABC):
    """Base interface for all LLM backends."""

    @abstractmethod
    async def generate(self, query: str, context: str) -> str:
        """Generate an answer for the query given the context."""

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        """Stream answer tokens. Default: yield the full answer at once."""
        answer = await self.generate(query, context)
        yield answer


# ── Mock backend (testing only — not used by build_generator) ────────────────

class MockGenerator(LLMGenerator):
    """Returns a deterministic mock answer. Used in unit tests only."""

    async def check_health(self) -> dict:
        return {"provider": "mock", "ok": True}

    async def generate(self, query: str, context: str) -> str:
        log.info("MockGenerator: returning stub answer")
        pages = []
        for part in context.split("\n"):
            if part.startswith("[Page "):
                try:
                    page = int(part.split("]")[0].replace("[Page ", ""))
                    pages.append(str(page))
                except ValueError:
                    pass
        page_ref = f" (pages {', '.join(pages)})" if pages else ""
        return f"Mock answer to: '{query}'{page_ref}. Based on the provided context."


# ── Factory ───────────────────────────────────────────────────────────────────

def build_generator(provider: Optional[str] = None) -> LLMGenerator:
    """
    Return the OpenRouter LLM backend — unconditionally.

    The `provider` argument is accepted for backward compatibility and ignored.
    Raises RuntimeError on first use if OPENROUTER_API_KEY is missing
    (see OpenRouterGenerator); importing this module never raises.
    """
    from .openrouter_generator import OpenRouterGenerator

    return OpenRouterGenerator()
