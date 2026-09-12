"""
tests/test_api_query.py
Integration tests for the query endpoint using MockGenerator.
Patches the LLM so no OpenRouter API key is needed.
"""
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_query_missing_auth(test_client):
    """Requests without X-API-Key should be rejected."""
    from httpx import AsyncClient, ASGITransport
    from ..main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post("/api/v1/query/", json={"question": "test?"})
    assert resp.status_code == 422  # Missing required header


@pytest.mark.asyncio
async def test_query_short_question_rejected(test_client):
    """Questions shorter than 3 chars should fail validation."""
    resp = await test_client.post("/api/v1/query/", json={"question": "hi"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_query_returns_answer_with_mock_llm(test_client):
    """Full query pipeline with MockGenerator (no API key needed)."""
    with patch("app.services.query_service.build_generator") as mock_build:
        from ..llm.generator import MockGenerator
        mock_build.return_value = MockGenerator()

        resp = await test_client.post(
            "/api/v1/query/",
            json={"question": "What is this document about?"},
        )

    # Will return grounded=False if no docs are indexed (empty DB) — that's fine
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "citations" in data
    assert "conversation_id" in data
    assert isinstance(data["grounded"], bool)
