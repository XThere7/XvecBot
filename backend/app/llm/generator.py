"""
llm/generator.py
LLM generation wrapper. Supports two backends:
  1. Ollama  — HTTP API, recommended (run `ollama serve` + `ollama pull llama3.2`)
  2. Mock    — Returns a dummy answer; used in tests / when no LLM is available

To switch backends, set LLM_PROVIDER in .env:
  LLM_PROVIDER=ollama  (default)
  LLM_PROVIDER=mock    (testing)

Adding a new backend (e.g. llama-cpp-python, OpenAI-compatible endpoint):
  - Implement the LLMGenerator protocol
  - Add the provider key to build_generator()
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from ..core.config import settings
from ..core.logging import get_logger
from .prompts import build_rag_prompt

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


# ── Ollama backend ────────────────────────────────────────────────────────────

class OllamaGenerator(LLMGenerator):
    """
    Calls a locally-running Ollama server.
    Start Ollama with: ollama serve
    Pull model with:   ollama pull llama3.2
    """
    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        max_tokens: int = None,
        temperature: float = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.temperature = temperature if temperature is not None else settings.llm_temperature

    async def generate(self, query: str, context: str) -> str:
        prompt = build_rag_prompt(query, context)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        log.info("Calling Ollama", model=self.model, url=self.base_url)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        answer = data.get("response", "").strip()
        log.info("Ollama response received", tokens=len(answer.split()))
        return answer

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        prompt = build_rag_prompt(query, context)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        import json
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break


# ── Mock backend (testing) ────────────────────────────────────────────────────

class MockGenerator(LLMGenerator):
    """Returns a deterministic mock answer. Used in unit tests."""

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
    Instantiate the correct LLM backend based on configuration.
    Import this in services/query_service.py — never import backends directly.
    """
    p = provider or settings.llm_provider
    if p == "ollama":
        return OllamaGenerator()
    elif p == "mock":
        return MockGenerator()
    else:
        raise ValueError(f"Unknown LLM provider: '{p}'. Choose 'ollama' or 'mock'.")
