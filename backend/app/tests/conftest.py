"""
tests/conftest.py
Shared pytest fixtures for all test modules.

Isolation (Phase 3): the suite runs against a throwaway SQLite file under
tempfile.gettempdir(), NEVER the developer's real data/rag.db. This works
because pytest always imports this conftest before any test module, and the
DATABASE_URL/UPLOAD_DIR env vars are set below before `app` (and its cached
settings + frozen _DB_PATH) is imported for the first time. Pydantic gives
real env vars precedence over the .env file, so no .env changes are needed.
"""
import asyncio
import os
import tempfile

# ── Must run before `from ..main import app` (settings freeze at import) ──
_TEST_DIR = tempfile.mkdtemp(prefix="xvec-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test_rag.db"
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_DIR, "uploads")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from ..main import app
from ..core.database import init_db, get_db
from ..core.config import settings


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _isolated_db():
    """Create the full schema once in the temp DB (lifespan never runs here)."""
    await init_db()
    yield


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
