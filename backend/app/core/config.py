"""
core/config.py
Central configuration loaded from .env via pydantic-settings.
All other modules import `settings` from here — never read os.environ directly.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve project root reliably regardless of cwd (backend/app/core -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_CANDIDATES = [
    _PROJECT_ROOT / ".env",           # project root .env (production-rag/.env)
    Path.cwd() / ".env",              # current working directory
    Path(__file__).resolve().parents[2] / ".env",  # backend/.env
]


def _resolve_env_file() -> str | None:
    for candidate in _ENV_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    # Fallback: let pydantic try default .env (will use defaults if missing)
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "production-rag"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── Security ─────────────────────────────────────────────────────────────
    api_key: str = "dev-key"
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/rag.db"
    vector_db_path: str = "./data/embeddings/vectors.db"

    # ── Storage ──────────────────────────────────────────────────────────────
    upload_dir: str = "./data/uploads"
    processed_dir: str = "./data/processed"

    # ── Embedding ────────────────────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # ── Reranker ─────────────────────────────────────────────────────────────
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64

    # ── Retrieval ────────────────────────────────────────────────────────────
    retrieval_top_k: int = 20
    rerank_top_k: int = 5
    rrf_k: int = 60

    # ── LLM (OpenRouter — sole provider) ─────────────────────────────────────
    # Cloud chat-completions API. Get a key at https://openrouter.ai/keys
    # and paste it into .env as OPENROUTER_API_KEY. Missing key raises on
    # first use (per-request), never on import.
    openrouter_api_key: str = ""
    openrouter_model: str = "inclusionai/ling-3.0-flash-fin:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.1

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Include loopback variants + current LAN IP. The regex in main.py covers
    # any future 192.168.x.x / 10.x.x.x DHCP change, this list is the explicit base.
    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://192.168.1.27:5173,http://192.168.1.27:3000"
    )

    # ── Derived helpers ──────────────────────────────────────────────────────
    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def _resolve_path(self, raw: str) -> Path:
        """Resolve relative paths against project root, support absolute paths."""
        p = Path(raw)
        if p.is_absolute():
            return p
        # Relative paths resolve against project root (consistent regardless of cwd)
        return (_PROJECT_ROOT / raw).resolve()

    @property
    def upload_path(self) -> Path:
        p = self._resolve_path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def processed_path(self) -> Path:
        p = self._resolve_path(self.processed_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vector_db_path_resolved(self) -> Path:
        p = self._resolve_path(self.vector_db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def database_path(self) -> Path:
        # Handle sqlite:/// prefix
        raw = self.database_url.replace("sqlite:///", "")
        p = Path(raw)
        if p.is_absolute():
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        resolved = (_PROJECT_ROOT / raw).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — cached after first call."""
    return Settings()


settings = get_settings()
