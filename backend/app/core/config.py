"""
core/config.py
Central configuration loaded from .env via pydantic-settings.
All other modules import `settings` from here — never read os.environ directly.
"""
from functools import lru_cache
from pathlib import Path
from typing import ClassVar
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
    app_name: str = "XvecBot"
    app_version: str = "1.0.0"
    debug: bool = False
    app_public_url: str = "https://yourplatform.com"
    # Point customer snippets at the minified bundle built by
    # scripts/build_widget.py. Set false to hand out the readable source.
    widget_minified: bool = True

    # ── Security ─────────────────────────────────────────────────────────────
    api_key: str = "dev-key"
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    # Serve /docs + /redoc. Default True for local dev; production sets
    # ENABLE_DOCS=false (BEARER tokens in docs "Authorize" are a leak vector).
    enable_docs: bool = True

    INSECURE_SECRET_DEFAULTS: ClassVar[tuple] = ("change-this-in-production", "", "dev-key")

    def secrets_are_default(self) -> bool:
        """True when SECRET_KEY is still an insecure placeholder."""
        return (self.SECRET_KEY or "").strip() in self.INSECURE_SECRET_DEFAULTS

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/rag.db"
    vector_db_path: str = "./data/embeddings/vectors.db"  # legacy (unused) — see Phase 2
    # Postgres pool (Neon). Only used when database_url is postgresql://…
    pg_pool_min_size: int = 2
    pg_pool_max_size: int = 10

    # ── Storage ──────────────────────────────────────────────────────────────
    upload_dir: str = "./data/uploads"
    UPLOAD_DIR: str = "./uploads"      # Phase 2 workspace uploads root
    processed_dir: str = "./data/processed"

    # ── Object storage (Phase 2: R2/S3 presigned uploads) ─────────────────
    # Local disk stays the default. S3/R2 activates only when S3_BUCKET is set
    # (plus credentials + endpoint for R2). Presigned flow never routes bytes
    # through FastAPI; the legacy UploadFile endpoints keep working unchanged.
    storage_backend: str = "auto"  # auto | local | s3
    s3_bucket: str = ""
    s3_prefix: str = "xvecbot"
    s3_endpoint_url: str = ""  # R2: https://<accountid>.r2.cloudflarestorage.com
    s3_region: str = "auto"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    presigned_put_expires: int = 900  # 15 min
    presigned_get_expires: int = 900  # 15 min
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB (mirrors legacy upload.py)

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
    # Used automatically when the primary model fails for a retryable reason
    # (rate limit, model unavailable, upstream 5xx, network error).
    # Set to "" to disable fallback. Env var: LLM_FALLBACK_MODEL
    llm_fallback_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_max_tokens: int = 4096
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
    def workspace_upload_path(self) -> Path:
        p = self._resolve_path(self.UPLOAD_DIR)
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
        if self.is_postgres:
            raise RuntimeError(
                "database_path is SQLite-only; use asyncpg_dsn on Postgres"
            )
        # Handle sqlite:/// prefix
        raw = self.database_url.replace("sqlite:///", "")
        p = Path(raw)
        if p.is_absolute():
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        resolved = (_PROJECT_ROOT / raw).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    # ── Postgres helpers (Neon production) ─────────────────────────────────
    @property
    def is_postgres(self) -> bool:
        """True when DATABASE_URL points at Postgres (Neon/RDS/Cloud SQL)."""
        u = (self.database_url or "").strip().lower()
        return u.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://"))

    @property
    def asyncpg_dsn(self) -> str:
        """DSN for asyncpg: strip any +asyncpg driver prefix."""
        u = (self.database_url or "").strip()
        if u.lower().startswith("postgresql+asyncpg://"):
            u = "postgresql://" + u.split("://", 1)[1]
        return u

    # ── Object-storage helpers ─────────────────────────────────────────────
    @property
    def is_s3_configured(self) -> bool:
        """True only when a bucket (+ R2 endpoint/credentials if needed) is set."""
        if not (self.s3_bucket or "").strip():
            return False
        if (self.storage_backend or "auto").strip().lower() == "local":
            return False
        return True

    @property
    def use_s3_storage(self) -> bool:
        """Effective switch: explicit 's3' forces, 'auto' follows configuration."""
        mode = (self.storage_backend or "auto").strip().lower()
        if mode == "s3":
            return True
        if mode == "local":
            return False
        return self.is_s3_configured


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — cached after first call."""
    return Settings()


settings = get_settings()
