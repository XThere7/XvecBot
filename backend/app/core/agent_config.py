"""
core/agent_config.py
Single source of truth for agent configuration constraints.

Purely functional — no database access, no FastAPI dependencies. Every rule
about what constitutes a valid agent configuration lives here so that services,
API layers and future phases all validate against the same definitions.

Design notes (extensibility):
  - Models are stored as a dict keyed by model id, with metadata per entry.
    Adding a paid tier later means adding entries with "tier": "paid" — no
    structural change required.
  - Languages are a simple list; adding one is a one-line change.
  - Rate limits per tier can be added as metadata on the model entries and
    consumed by a future limiter without touching this module's callers.
"""
from ..core.logging import get_logger
from typing import Optional

log = get_logger(__name__)


# ── 1. Supported models ──────────────────────────────────────────────────────
#
# Dict keyed by the OpenRouter model id. Each entry carries metadata so new
# tiers (paid models, rate limits, context windows) can be introduced without
# changing the structure or the callers.
SUPPORTED_MODELS: dict[str, dict] = {
    "meta-llama/llama-3.3-70b-instruct:free": {
        "name": "Llama 3.3 70B Instruct",
        "tier": "free",
        "max_tokens": 4096,
    },
    "qwen/qwen3-235b-a22b:free": {
        "name": "Qwen3 235B A22B",
        "tier": "free",
        "max_tokens": 4096,
    },
    "google/gemma-3-27b-it:free": {
        "name": "Gemma 3 27B IT",
        "tier": "free",
        "max_tokens": 4096,
    },
    "openrouter/free": {
        "name": "OpenRouter Auto (free)",
        "tier": "free",
        "max_tokens": 4096,
    },
}

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def is_model_allowed(model_string: str) -> bool:
    """True if the model id is in the supported list."""
    return model_string in SUPPORTED_MODELS


# ── 2. Temperature constraints ───────────────────────────────────────────────

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 1.0
DEFAULT_TEMPERATURE = 0.7


def validate_temperature(value: float) -> float:
    """
    Clamp a temperature into [MIN_TEMPERATURE, MAX_TEMPERATURE].

    Never raises — an out-of-range value is clamped and a warning is logged so
    the caller can store a valid value without a round-trip.
    """
    if value < MIN_TEMPERATURE:
        log.warning(
            "Temperature below minimum, clamping",
            value=value,
            minimum=MIN_TEMPERATURE,
        )
        return MIN_TEMPERATURE
    if value > MAX_TEMPERATURE:
        log.warning(
            "Temperature above maximum, clamping",
            value=value,
            maximum=MAX_TEMPERATURE,
        )
        return MAX_TEMPERATURE
    return value


# ── 3. Supported languages ───────────────────────────────────────────────────

SUPPORTED_LANGUAGES = ["English", "Swahili", "French", "Arabic", "Portuguese"]

DEFAULT_LANGUAGE = "English"


def is_language_supported(language: str) -> bool:
    """Case-insensitive membership check against the supported languages."""
    if not language:
        return False
    return language.strip().lower() in {lang.lower() for lang in SUPPORTED_LANGUAGES}


# ── 4. Default agent configuration ───────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional, customer-facing assistant. Answer clearly and "
    "concisely, using only the knowledge provided to you. If the answer is not "
    "available, say so honestly and offer to connect the user with a human. "
    "Be polite, stay on topic, and never invent information."
)


def get_agent_defaults() -> dict:
    """A ready-to-use, valid default agent configuration."""
    return {
        "model": DEFAULT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
        "language": DEFAULT_LANGUAGE,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


# ── 5. Agent config validator ────────────────────────────────────────────────

MAX_NAME_LENGTH = 100
MIN_SYSTEM_PROMPT_LENGTH = 10


def validate_agent_config(
    name: str,
    system_prompt: str,
    model: str,
    temperature: float,
    language: str,
) -> dict:
    """
    Validate and normalise a full agent configuration.

    Raises ValueError for hard violations (name/system_prompt length).
    Soft violations (unsupported model or language) fall back to defaults with
    a warning, so the returned dict is always storable.

    Returns a clean dict with keys: name, system_prompt, model, temperature,
    language.
    """
    # Name — hard validation
    if not name or not name.strip():
        raise ValueError("Agent name must not be empty.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"Agent name must be at most {MAX_NAME_LENGTH} characters "
            f"(got {len(name)})."
        )

    # System prompt — hard validation
    if not system_prompt or not system_prompt.strip():
        raise ValueError("System prompt must not be empty.")
    if len(system_prompt) < MIN_SYSTEM_PROMPT_LENGTH:
        raise ValueError(
            f"System prompt must be at least {MIN_SYSTEM_PROMPT_LENGTH} "
            f"characters (got {len(system_prompt)})."
        )

    # Model — soft validation (fall back to default)
    if not is_model_allowed(model):
        log.warning(
            "Unsupported model, falling back to default",
            model=model,
            default=DEFAULT_MODEL,
        )
        model = DEFAULT_MODEL

    # Temperature — clamp
    temperature = validate_temperature(temperature)

    # Language — soft validation (fall back to default)
    if not is_language_supported(language):
        log.warning(
            "Unsupported language, falling back to default",
            language=language,
            default=DEFAULT_LANGUAGE,
        )
        language = DEFAULT_LANGUAGE

    return {
        "name": name.strip(),
        "system_prompt": system_prompt,
        "model": model,
        "temperature": temperature,
        "language": language,
    }
