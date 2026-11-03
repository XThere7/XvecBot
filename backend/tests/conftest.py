"""Isolation for the website feature tests.

This directory is intentionally outside ``app/tests`` so the historical
baseline suite keeps its exact pass/skip/fail counts. Run these with:

    cd backend
    PYTHONPATH=. ../path/to/python -m pytest tests -q
"""
import asyncio
import os
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="botbase-website-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test_rag.db"
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_DIR, "uploads")
os.environ["DEFAULT_WORKSPACE_PLAN"] = "pro"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _isolated_db():
    await init_db()
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as http:
        yield http
