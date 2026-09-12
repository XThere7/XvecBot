"""
llm/openrouter_generator.py
OpenRouter backend — the sole LLM provider for this project.

Uses the OpenAI-compatible chat-completions endpoint:
    POST {OPENROUTER_BASE_URL}/chat/completions

Auth:  Authorization: Bearer ${OPENROUTER_API_KEY}
Extra recommended headers:
    HTTP-Referer: http://localhost:5173 (dev)
    X-Title: RAG Project

Same LLMGenerator interface as before: generate(query, context) and
stream(query, context). The prompt keeps the existing RAG structure
(system rules + --- DOCUMENT CONTEXT --- + [Page N] chunks + question).
"""
import json
from typing import Any, AsyncIterator, Optional

import httpx

from ..core.config import settings
from ..core.logging import get_logger
from .generator import LLMGenerator
from .prompts import SYSTEM_PROMPT

log = get_logger(__name__)

# Dev referer sent as HTTP-Referer (OpenRouter ranking/analytics header).
_DEFAULT_REFERER = "http://localhost:5173"
_DEFAULT_TITLE = "RAG Project"

MISSING_KEY_MSG = (
    "OPENROUTER_API_KEY is not set. "
    "Paste your key into .env (get one at https://openrouter.ai/keys), "
    "restart the backend, and retry."
)


def _friendly_http_error(status: int, body: str, model: str) -> RuntimeError:
    """Map OpenRouter HTTP failures to actionable messages for the UI."""
    snippet = (body or "").strip()[:300]
    if status == 401:
        return RuntimeError(
            "OpenRouter rejected the API key (HTTP 401). "
            "Check OPENROUTER_API_KEY in .env — get a fresh key at "
            f"https://openrouter.ai/keys. Detail: {snippet}"
        )
    if status == 402:
        return RuntimeError(
            "OpenRouter account has no credits left (HTTP 402). "
            f"Top up at https://openrouter.ai/credits. Detail: {snippet}"
        )
    if status == 404:
        return RuntimeError(
            f"OpenRouter has no model named '{model}' (HTTP 404). "
            "Check OPENROUTER_MODEL in .env — e.g. "
            f"'inclusionai/ling-3.0-flash-fin:free'. Detail: {snippet}"
        )
    if status == 429:
        return RuntimeError(
            "OpenRouter rate limit hit (HTTP 429). "
            f"Wait a moment and retry. Detail: {snippet}"
        )
    return RuntimeError(f"OpenRouter returned HTTP {status}: {snippet}")


class OpenRouterGenerator(LLMGenerator):
    """Chat-completions generator backed by OpenRouter (httpx, no extra deps)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.timeout = timeout
        if not self.api_key:
            # Fail fast on first use (per-request construction), never on import.
            raise RuntimeError(MISSING_KEY_MSG)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": _DEFAULT_REFERER,
            "X-Title": _DEFAULT_TITLE,
        }

    def _messages(self, query: str, context: str) -> list:
        user_content = (
            "Answer the question using ONLY the context below. "
            'If the answer is not in the context, reply exactly: "I cannot find '
            'the answer in the provided document."\n\n'
            f"--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
            f"Question: {query}"
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _payload(self, query: str, context: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": self._messages(query, context),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

    async def check_health(self) -> dict:
        """Diagnostics for GET /api/v1/query/llm/status — never raises."""
        result: dict[str, Any] = {
            "provider": "openrouter",
            "model": self.model if self.api_key else settings.openrouter_model,
            "base_url": self.base_url if self.api_key else settings.openrouter_base_url,
            "ok": False,
        }
        if not self.api_key:
            result["error"] = MISSING_KEY_MSG
            return result
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    result["ok"] = True
                else:
                    result["error"] = str(
                        _friendly_http_error(resp.status_code, resp.text, self.model)
                    )
        except Exception as exc:
            result["error"] = f"Cannot reach OpenRouter at {self.base_url}: {exc}"
        return result

    async def generate(self, query: str, context: str) -> str:
        log.info("Calling OpenRouter", model=self.model)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(query, context, stream=False),
                )
                if resp.status_code != 200:
                    raise _friendly_http_error(resp.status_code, resp.text, self.model)
                data = resp.json()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc}") from exc
        try:
            answer = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise RuntimeError(
                f"OpenRouter returned an unexpected response shape: {str(data)[:300]}"
            ) from exc
        if not answer:
            raise RuntimeError("OpenRouter returned an empty response.")
        log.info("OpenRouter response received", tokens=len(answer.split()))
        return answer

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(query, context, stream=True),
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise _friendly_http_error(
                            resp.status_code,
                            body.decode("utf-8", errors="replace"),
                            self.model,
                        )
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        if not payload:
                            continue
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("error"):
                            raise RuntimeError(f"OpenRouter error: {chunk['error']}")
                        try:
                            delta = chunk["choices"][0]["delta"].get("content", "")
                        except (KeyError, IndexError):
                            continue
                        if delta:
                            yield delta
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"OpenRouter stream failed: {exc}") from exc
