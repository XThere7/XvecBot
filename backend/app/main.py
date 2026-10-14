"""
main.py
FastAPI application factory and entry point.

Architecture:
  FastAPI handles:  HTTP routing, auth, validation, CORS, monitoring
  LangGraph handles: RAG pipeline (retrieve -> rerank -> ground -> generate -> cite)

Start dev server:
  cd backend && uvicorn app.main:app --reload --port 8000

API docs (auto-generated):
  http://localhost:8000/docs
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .api import agents, api_keys, auth, developer, documents, embed_tokens, health, public, query, upload, workspaces
from .core.config import settings
from .core.database import init_db
from .core.logging import get_logger, setup_logging
from .core.middleware import PublicSurfaceMiddleware
from .core.rate_limit import RateLimitMiddleware

# Initialise structured logging first
setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    startup:  Initialise DB schema + warm up the embedding model.
    shutdown: Clean up resources.

    NOTE: the LLM is OpenRouter (cloud API) — there is no local model to
    preload, warm up, or health-ping at startup.
    """
    log.info("Starting up", app=settings.app_name, version=settings.app_version)

    # Fail fast on insecure secrets in non-debug mode. Local dev (DEBUG=true)
    # keeps the placeholder so first-run stays frictionless; production with
    # DEBUG=false and a default SECRET_KEY refuses to boot rather than
    # signing JWTs with a public value.
    if not settings.debug and settings.secrets_are_default():
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is still the insecure default. "
            "Set a 32+ byte SECRET_KEY env var (DEBUG=false requires it)."
        )

    # Create DB tables + load sqlite-vec extension
    await init_db()

    # Warm up embedding model (loads weights into memory on first call)
    # Non-fatal: if model download fails / no network, log and continue
    # so /health and /docs remain usable without embeddings.
    try:
        log.info("Warming up embedding model...")
        from .ingestion.embedder import embed_texts
        embed_texts(["warm up"])
        log.info("Embedding model ready")
    except Exception as exc:
        log.warning("Embedding warmup skipped — will lazy-load on first query", error=str(exc))

    log.info("Application startup complete")
    yield

    log.info("Application shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Production RAG with Citations",
        description=(
            "A production-grade PDF Q&A system using hybrid search, "
            "cross-encoder reranking, grounding, and page-level citations. "
            "Built with LangGraph + FastAPI + SQLite-vec."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        # Hidden in production (ENABLE_DOCS=false) — interactive docs with
        # an Authorize button are a token-phishing surface on public hosts.
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    # The dashboard API is intentionally restricted to the configured dev
    # origins: its JWT endpoints should not be callable from arbitrary sites.
    # That policy is also too strict for /public/*, which the embedded widget
    # calls from whatever domain a customer pastes the snippet into — Starlette's
    # CORSMiddleware answers a disallowed preflight with 400 before any route
    # runs, so the widget simply would not work on a real customer domain.
    # PublicSurfaceMiddleware opens CORS for /public/* only and leaves every
    # other route to this restrictive policy. Per-widget origin allow-listing is
    # enforced at the application layer in embed_service._check_origin().
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # Registered last => outermost (Starlette inserts at index 0), so this layer
    # answers /public/* preflights before CORSMiddleware can reject them.
    app.add_middleware(PublicSurfaceMiddleware)
    # Outermost of all: reject abusive traffic before any other work.
    # Env-gated (RATE_LIMIT_ENABLED, default off) and scoped to /auth/* +
    # /public/*, so local dev, tests, and dashboard routes never notice it.
    app.add_middleware(
        RateLimitMiddleware,
        enabled=settings.rate_limit_enabled,
        per_minute=settings.rate_limit_per_minute,
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(documents.router)
    app.include_router(agents.router)
    app.include_router(public.router)
    app.include_router(embed_tokens.router)
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(query.router,  prefix="/api/v1")
    # Phase 6 developer platform. Paths (/chat, /agents, /health) do not
    # collide with the legacy query router (/ , /stream, /llm/status,
    # /conversations/{id}); api_keys lives under /workspaces alongside the
    # agents/documents/embed_tokens routers with distinct segments.
    app.include_router(developer.router)
    app.include_router(api_keys.router)

    # ── Static ───────────────────────────────────────────────────────────────
    # The embeddable widget script, served at https://<host>/widget.js so the
    # snippet can point straight at it. Mounted last so it never shadows a route.
    # static_dir is an absolute path (resolved from this file), not a relative
    # "app/static" — a relative directory only resolves when the process cwd
    # happens to be backend/, and StaticFiles raises at startup if it is missing.
    # The same directory is also mounted under /static/widget.js, which is the
    # path the Phase 4 integration test and several CDNs expect.
    # ── Bot icons ─────────────────────────────────────────────────────────────
    # Agent avatars uploaded via POST .../agents/{id}/icon live under the
    # workspace upload root and are served at /static/icons/<agent>/<file> so
    # the widget (any customer domain) can load them as <img> URLs. The dir is
    # created here so the mount never fails on a fresh deploy. Mounted BEFORE
    # the generic /static mount below — Starlette matches in order and /static
    # would otherwise swallow /static/icons/* and 404 against widget.js's dir.
    icons_dir = settings.workspace_upload_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static/icons", StaticFiles(directory=str(icons_dir), html=False), name="icons")

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")
        app.mount("/", StaticFiles(directory=str(static_dir), html=False), name="widget")

    return app


app = create_app()
