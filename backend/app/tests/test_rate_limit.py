"""
tests/test_rate_limit.py (Phase 4)
Env-gated abuse mitigation: off by default (dev/tests never throttled),
scoped to /auth/* + /public/* when enabled.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..core.config import settings
from ..main import app


@pytest.mark.asyncio
async def test_rate_limit_off_by_default():
    """Default config: burst registrations are never throttled."""
    assert settings.rate_limit_enabled is False
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(4):
            r = await client.post(
                "/auth/register",
                json={
                    "email": f"rl-off-{uuid.uuid4().hex[:8]}@example.com",
                    "password": "pw123456",
                },
            )
            assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_rate_limit_kicks_in_when_enabled(monkeypatch):
    """Enabled with limit 2: third /auth hit in a minute is 429 + Retry-After."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            codes = []
            for _ in range(3):
                r = await client.post(
                    "/auth/register",
                    json={
                        "email": f"rl-on-{uuid.uuid4().hex[:8]}@example.com",
                        "password": "pw123456",
                    },
                )
                codes.append(r.status_code)
            assert codes[:2] == [201, 201], codes
            assert codes[2] == 429, codes
            assert "retry-after" in {k.lower() for k in r.headers}, dict(r.headers)
            # Unscoped routes are never throttled, even when enabled.
            r = await client.get("/health")
            assert r.status_code == 200, r.text
    finally:
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
