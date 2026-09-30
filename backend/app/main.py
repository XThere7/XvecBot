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

from .api import agents, auth, documents, embed_tokens, health, public, query, upload, workspaces
from .core.config import settings
from .core.database import init_db
from .core.logging import get_logger, setup_logging
from .core.middleware import PublicSurfaceMiddleware

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
        docs_url="/docs",
        redoc_url="/redoc",
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

    # ── Static ───────────────────────────────────────────────────────────────
    # The embeddable widget script, served at https://<host>/widget.js so the
    # snippet can point straight at it. Mounted last so it never shadows a route.
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=False), name="widget")

    return app


app = create_app()
