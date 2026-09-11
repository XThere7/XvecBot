"""
tests/conftest.py
Shared pytest fixtures for all test modules.
Uses an in-memory SQLite DB so tests are isolated and fast.
"""
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from ..main import app
from ..core.database import init_db, get_db
from ..core.config import settings


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
