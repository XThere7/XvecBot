"""
tests/conftest.py
Shared pytest fixtures for all test modules.

Isolation (Phase 3): the suite runs against a throwaway SQLite file under
tempfile.gettempdir(), NEVER the developer's real data/rag.db. This works
because pytest always imports this conftest before any test module, and the
DATABASE_URL/UPLOAD_DIR env vars are set below before `app` (and its cached
settings + frozen _DB_PATH) is imported for the first time. Pydantic gives
real env vars precedence over the .env file, so no .env changes are needed.

Postgres mode (Stage 1): set BOTBASE_TEST_DATABASE_URL to a **throwaway**
Postgres database and the same suite runs against real PostgreSQL + pgvector,
so the asyncpg/pg_compat/pgvector code path is covered by the same tests
instead of being an untested blind spot:

    BOTBASE_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:5433/botbase_test \\
        PYTHONPATH=. .venv/bin/python -m pytest app/tests/ -q

The app tables are truncated when the session ends; the database itself is
never dropped (point it at a scratch database, not a production one).
"""
import asyncio
import os
import tempfile

# ── Must run before `from ..main import app` (settings freeze at import) ──
_TEST_DIR = tempfile.mkdtemp(prefix="botbase-test-")
_PG_TEST_URL = os.environ.get("BOTBASE_TEST_DATABASE_URL", "").strip()
if _PG_TEST_URL:
    # Opt-in: exercise the real PostgreSQL code path.
    os.environ["DATABASE_URL"] = _PG_TEST_URL
else:
    os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test_rag.db"
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_DIR, "uploads")
# Transactional email must never leave the process in the test suite: the
# memory backend keeps messages in a list that the email tests inspect.
os.environ["EMAIL_BACKEND"] = "memory"
# Existing suites create several agents per workspace and issue developer API
# keys. Run them on Pro so subscription limits do not interfere; the dedicated
# billing tests explicitly downgrade a workspace to Free.
os.environ["DEFAULT_WORKSPACE_PLAN"] = "pro"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from ..main import app
from ..core.database import init_db, get_db
from ..core.config import settings

_APP_TABLES = (
    "usage_monthly",
    "usage_events",
    "website_sync_jobs",
    "website_pages",
    "website_sources",
    "password_reset_tokens",
    "plan_changes",
    "payments",
    "platform_settings",
    "error_events",
    "messages",
    "conversations",
    "chunk_embeddings",
    "chunks",
    "workspace_documents",
    "documents",
    "agent_embed_tokens",
    "developer_api_keys",
    "agents",
    "workspaces",
    "users",
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _isolated_db():
    """Create the full schema once in the temp DB (lifespan never runs here)."""
    await init_db()
    if _PG_TEST_URL:
        # Make the scratch database look like a migrated one, so tooling that
        # checks alembic_version (the cutover preflight) behaves as it would
        # in production.
        async with get_db() as db:
            try:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL)"
                )
                await db.execute("DELETE FROM alembic_version")
                await db.execute(
                    "INSERT INTO alembic_version (version_num) VALUES (?)",
                    ("0012_admin_panel",),
                )
                await db.commit()
            except Exception:
                pass
    yield
    if _PG_TEST_URL:
        # Leave the scratch database clean for the next run.
        async with get_db() as db:
            for table in _APP_TABLES:
                try:
                    await db.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            await db.commit()


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_client():
    """AsyncClient wired to the FastAPI app with auth header."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
    ) as client:
        yield client
