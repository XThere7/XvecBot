"""
llm/openvino_generator.py
OpenVINO backend for low-RAM local inference.

Why this exists: a Qwen2.5 32B GGUF via Ollama needs ~20 GB RAM and OOMs an
11 GB machine (RAM spikes to 90%+, no answer ever arrives). The fix is a
smaller instruction model (3B, optionally 7B) pre-quantized to INT4 in
OpenVINO IR format, which runs on CPU (or Intel iGPU) in ~2 GB (3B) or
~4-5 GB (7B) of RAM.

Setup:
  1. pip install -r backend/requirements-openvino.txt
     (needs Python 3.10–3.13; use a venv with one of those versions)
  2. python scripts/download_openvino_model.py   # fetches INT4 IR to ./models/
  3. Set in .env:  LLM_PROVIDER=openvino
                   OPENVINO_MODEL_ID=./models/qwen2.5-3b-instruct-int4-ov
                   (or keep the Hugging Face ID to load straight from the Hub)

Notes:
  - OpenVINO cannot run Ollama's GGUF files — it needs OpenVINO IR. Use the
    pre-quantized IDs published by the OpenVINO org on Hugging Face, e.g.
    OpenVINO/Qwen2.5-3B-Instruct-int4-ov (recommended here),
    OpenVINO/Qwen2.5-7B-Instruct-int4-ov (max for ~11 GB RAM).
  - Do NOT point this at a 32B IR: even as INT4 it needs ~18 GB+ and will
    still OOM this machine.
  - Heavy deps (openvino, optimum-intel) are imported lazily so the rest of
    the backend (and the test-suite) works without them installed.
"""
import asyncio
from functools import lru_cache
from pathlib import Path
from threading import Thread
from typing import AsyncIterator

from ..core.config import settings
from ..core.logging import get_logger
from .generator import LLMGenerator
from .prompts import SYSTEM_PROMPT

log = get_logger(__name__)

MISSING_DEPS_MSG = (
    "OpenVINO dependencies are not installed. Run: "
    "pip install -r backend/requirements-openvino.txt "
    "(use Python 3.10–3.13 for OpenVINO support)."
)


@lru_cache(maxsize=1)
def _load_pipeline(model_id: str, device: str):
    """Load tokenizer + INT4 IR model once per process. Blocking — run in a thread."""
    try:
        from optimum.intel.openvino import OVModelForCausalLM
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(MISSING_DEPS_MSG) from exc

    log.info("Loading OpenVINO model", model=model_id, device=device)
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = OVModelForCausalLM.from_pretrained(
        model_id,
        device=device,
        ov_config={"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1"},
        trust_remote_code=True,
    )
    # Left padding + pad==eos is the standard causal-LM batching setup.
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    try:
        model.generation_config.pad_token_id = tokenizer.pad_token_id
    except Exception:
        pass
    log.info("OpenVINO model ready", model=model_id, device=device)
    return tokenizer, model


def _build_chat_prompt(tokenizer, query: str, context: str) -> str:
    """Render the Qwen chat template (system + user with RAG context)."""
    user_content = (
        "Answer the question using ONLY the context below. "
        'If the answer is not in the context, reply exactly: "I cannot find '
        'the answer in the provided document."\n\n'
        f"--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
        f"Question: {query}"
    )
    try:
        return tokenizer.apply_chat_template(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        # Fallback for tokenizers without a chat template.
        return f"{SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {query}\nAnswer:"


class OpenVINOLLMGenerator(LLMGenerator):
    """Qwen-Instruct INT4 via OpenVINO on CPU/iGPU. Same interface as Ollama."""

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.model_id = model_id or settings.openvino_model_id
        self.device = (device or settings.openvino_device).upper()
        self.max_new_tokens = max_new_tokens or settings.openvino_max_new_tokens
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )

    async def check_health(self) -> dict:
        """Diagnostics for GET /api/v1/query/llm/status — never raises."""
        result: dict = {
            "provider": "openvino",
            "model": self.model_id,
            "device": self.device,
            "ok": False,
        }
        try:
            import openvino  # noqa: F401
            import optimum.intel.openvino  # noqa: F401
            import transformers  # noqa: F401
            result["deps_installed"] = True
        except ImportError:
            result["deps_installed"] = False
            result["error"] = MISSING_DEPS_MSG
            return result
        p = Path(self.model_id)
        if p.is_dir():
            has_ir = any(p.glob("*.xml")) or any(p.rglob("openvino_model.xml"))
            result["model_cached_locally"] = bool(has_ir)
            result["ok"] = bool(has_ir)
            if not has_ir:
                result["error"] = (
                    f"Directory '{self.model_id}' has no OpenVINO IR (*.xml). "
                    "Run: python scripts/download_openvino_model.py"
                )
        else:
            # Hugging Face ID — downloadable on first use.
            result["model_cached_locally"] = False
            result["ok"] = True
            result["note"] = (
                "Model will be downloaded from Hugging Face on first request "
                "(~2 GB for the 3B INT4 model)."
            )
        return result

    def _generate_kwargs(self) -> dict:
        if self.temperature and self.temperature > 0:
            return {
                "max_new_tokens": self.max_new_tokens,
                "temperature": self.temperature,
                "do_sample": True,
                "top_p": 0.9,
            }
        return {"max_new_tokens": self.max_new_tokens, "do_sample": False}

    async def generate(self, query: str, context: str) -> str:
        def _run() -> str:
            import torch

            tokenizer, model = _load_pipeline(self.model_id, self.device)
            prompt = _build_chat_prompt(tokenizer, query, context)
            inputs = tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                out = model.generate(
                    inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    **self._generate_kwargs(),
                )
            # Strip the prompt tokens, decode only the completion.
            new_tokens = out[0][inputs["input_ids"].shape[-1]:]
            return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

        answer = await asyncio.to_thread(_run)
        if not answer:
            raise RuntimeError("OpenVINO model returned an empty response.")
        log.info("OpenVINO response received", tokens=len(answer.split()))
        return answer

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        """Token streaming via TextIteratorStreamer in a worker thread."""
        try:
            from transformers import TextIteratorStreamer
        except ImportError as exc:
            raise RuntimeError(MISSING_DEPS_MSG) from exc

        import torch

        tokenizer, model = await asyncio.to_thread(
            _load_pipeline, self.model_id, self.device
        )
        prompt = _build_chat_prompt(tokenizer, query, context)
        inputs = tokenizer(prompt, return_tensors="pt")
        streamer = TextIteratorStreamer(tokenizer, skip_special_tokens=True)

        gen_kwargs = dict(
            input_ids=inputs["input_ids"],
            attention_mask=inputs.get("attention_mask"),
            streamer=streamer,
            **self._generate_kwargs(),
        )

        def _run():
            with torch.no_grad():
                model.generate(**gen_kwargs)

        thread = Thread(target=_run, daemon=True)
        thread.start()
        for token in streamer:
            yield token
        thread.join()
