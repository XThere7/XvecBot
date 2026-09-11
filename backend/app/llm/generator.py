"""
llm/generator.py
LLM generation wrapper. Supports three backends:
  1. Ollama   — HTTP API, default (run `ollama serve` + `ollama pull qwen2.5:3b`)
  2. OpenVINO — local INT4 inference on CPU/iGPU, low RAM (LLM_PROVIDER=openvino)
  3. Mock     — Returns a dummy answer; used in tests / when no LLM is available

To switch backends, set LLM_PROVIDER in .env:
  LLM_PROVIDER=ollama    (default)
  LLM_PROVIDER=openvino  (needs requirements-openvino.txt + downloaded IR model)
  LLM_PROVIDER=mock      (testing)

Adding a new backend (e.g. llama-cpp-python, OpenAI-compatible endpoint):
  - Implement the LLMGenerator protocol
  - Add the provider key to build_generator()
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

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
    Pull model with:   ollama pull qwen2.5:3b

    NOTE on model size: Qwen2.5 comes in 0.5/1.5/3/7/14/32/72B (there is no
    "35b" — that name means the 32B variant). A 32B Q4 model needs ~20 GB RAM
    and will OOM / hang on an 11 GB machine. Use qwen2.5:3b (≈2 GB) or at most
    qwen2.5:7b (≈5 GB) on this hardware.
    """
    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        max_tokens: int = None,
        temperature: float = None,
        timeout: float = None,
        num_ctx: int = None,
        keep_alive: str = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.timeout = timeout or settings.ollama_timeout
        self.num_ctx = num_ctx or settings.ollama_num_ctx
        self.keep_alive = keep_alive or settings.ollama_keep_alive

    def _payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "num_ctx": self.num_ctx,
            },
        }

    def _friendly_error(self, exc: Exception) -> RuntimeError:
        """Map low-level httpx/Ollama errors to actionable messages for the UI."""
        if isinstance(exc, httpx.ConnectError):
            return RuntimeError(
                f"Cannot reach Ollama at {self.base_url}. "
                "Is `ollama serve` running on this machine?"
            )
        if isinstance(exc, httpx.TimeoutException):
            return RuntimeError(
                f"Ollama timed out after {self.timeout:g}s waiting for '{self.model}'. "
                "The model is likely too large for this machine (RAM spiking to 90%+ "
                "is the tell-tale sign) or the RAG context is too long. "
                "Fix: use a smaller model (`ollama pull qwen2.5:3b`), lower "
                "OLLAMA_NUM_CTX / LLM_MAX_TOKENS, or raise OLLAMA_TIMEOUT."
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            body = ""
            try:
                body = exc.response.text[:300]
            except Exception:
                pass
            if status == 404 and "model" in body.lower():
                return RuntimeError(
                    f"Ollama has no model named '{self.model}' ({body.strip()}). "
                    f"Run `ollama pull {self.model}` or set OLLAMA_MODEL to one of "
                    "your installed models (`ollama list`). Note: there is no "
                    "'qwen2.5:35b' — the 32B variant is 'qwen2.5:32b' and needs "
                    "~20 GB RAM, which this machine does not have."
                )
            return RuntimeError(f"Ollama returned HTTP {status}: {body.strip()}")
        return RuntimeError(f"Ollama request failed: {exc}")

    async def _available_models(self, client: httpx.AsyncClient) -> list[str]:
        try:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:
            return []

    async def check_health(self) -> dict:
        """Diagnostics for GET /api/v1/query/llm/status — never raises."""
        result: dict[str, Any] = {
            "provider": "ollama",
            "base_url": self.base_url,
            "configured_model": self.model,
            "ok": False,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                models = await self._available_models(client)
                result["reachable"] = True
                result["available_models"] = models
                result["model_available"] = any(
                    m == self.model or m.startswith(self.model + ":")
                    or self.model.startswith(m)
                    for m in models
                )
                result["ok"] = result["model_available"]
                if not result["model_available"]:
                    result["error"] = (
                        f"Model '{self.model}' is not pulled. "
                        f"Run `ollama pull {self.model}`."
                    )
        except Exception as exc:
            result["reachable"] = False
            result["model_available"] = False
            result["error"] = str(self._friendly_error(exc))
        return result

    async def generate(self, query: str, context: str) -> str:
        prompt = build_rag_prompt(query, context)
        log.info("Calling Ollama", model=self.model, url=self.base_url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=self._payload(prompt, stream=False),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise self._friendly_error(exc) from exc
        answer = data.get("response", "").strip()
        if not answer:
            raise RuntimeError(
                f"Ollama returned an empty response for '{self.model}'. "
                "The model may have run out of memory — check `ollama ps` and RAM usage."
            )
        log.info("Ollama response received", tokens=len(answer.split()))
        return answer

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        prompt = build_rag_prompt(query, context)
        import json
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/generate",
                    json=self._payload(prompt, stream=True),
                ) as resp:
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise self._friendly_error(exc) from exc
                    async for line in resp.aiter_lines():
                        if line.strip():
                            chunk = json.loads(line)
                            if chunk.get("error"):
                                raise RuntimeError(f"Ollama error: {chunk['error']}")
                            token = chunk.get("response", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
        except RuntimeError:
            raise
        except Exception as exc:
            raise self._friendly_error(exc) from exc


# ── Mock backend (testing) ────────────────────────────────────────────────────

class MockGenerator(LLMGenerator):
    """Returns a deterministic mock answer. Used in unit tests."""

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
    Instantiate the correct LLM backend based on configuration.
    Import this in services/query_service.py — never import backends directly.
    """
    p = provider or settings.llm_provider
    if p == "ollama":
        return OllamaGenerator()
    elif p == "openvino":
        from .openvino_generator import OpenVINOLLMGenerator
        return OpenVINOLLMGenerator()
    elif p == "mock":
        return MockGenerator()
    else:
        raise ValueError(
            f"Unknown LLM provider: '{p}'. Choose 'ollama', 'openvino' or 'mock'."
        )
