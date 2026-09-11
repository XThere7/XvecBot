"""
tests/test_api_health.py
Integration tests for health endpoints.
"""
import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_health_ok(test_client):
    resp = await test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_readiness_ok(test_client):
    resp = await test_client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ready", "not_ready")
    assert "database" in data
