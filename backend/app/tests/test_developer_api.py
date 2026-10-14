"""
tests/test_developer_api.py (Phase 6 — BotBase developer platform).

Covers everything that does not need the LLM/embedding weights: key lifecycle
(create-once-full-key, prefix-only listings, update, revoke, delete), auth
shapes (flat {"error"}), workspace + allowed_agents scoping, inactive-agent
404, validation 400s, expiry, the per-key rate limiter unit, and the agents
discovery endpoint. Live chat (TEST-09/10) runs in the manual script below.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, ASGITransport

from ..api.developer import _check_dev_rate_limit
from ..main import app
from ..services.api_key_service import generate_api_key


async def _register(client, tag):
    email = f"dev-{tag}@example.com"
    r = await client.post(
        "/auth/register", json={"email": email, "password": "pw123456"}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _workspace(client, headers, name="ws"):
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _agent(client, headers, ws_id, name="agent"):
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": name, "system_prompt": "Be helpful always."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _make_key(client, headers, ws_id, **body):
    payload = {"name": f"k-{uuid.uuid4().hex[:6]}"}
    payload.update(body)
    r = await client.post(
        f"/workspaces/{ws_id}/api-keys", json=payload, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_generate_api_key_format():
    full, digest, prefix = generate_api_key()
    assert full.startswith("sk-botbase-") and len(full) == 11 + 40
    assert len(digest) == 64 and digest != full
    assert prefix == full[:12]


@pytest.mark.asyncio
async def test_dev_health_no_auth():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok" and body["version"] == "1.0"
        assert "docs" in body


@pytest.mark.asyncio
async def test_key_lifecycle_shows_full_key_once():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        created = await _make_key(client, headers, ws_id)

        assert created["key"].startswith("sk-botbase-")
        assert created["key_prefix"] == created["key"][:12]
        assert "warning" in created and "Save this key" in created["warning"]

        listed = (
            await client.get(f"/workspaces/{ws_id}/api-keys", headers=headers)
        ).json()
        assert len(listed) == 1
        dumped = str(listed)
        assert created["key"] not in dumped  # full key never reappears
        assert "key_hash" not in dumped
        assert listed[0]["key_prefix"] == created["key_prefix"]

        one = (
            await client.get(
                f"/workspaces/{ws_id}/api-keys/{created['id']}", headers=headers
            )
        ).json()
        assert "key" not in one and "key_hash" not in str(one)

        updated = (
            await client.put(
                f"/workspaces/{ws_id}/api-keys/{created['id']}",
                json={"name": "renamed"},
                headers=headers,
            )
        ).json()
        assert updated["name"] == "renamed"

        r = await client.delete(
            f"/workspaces/{ws_id}/api-keys/{created['id']}", headers=headers
        )
        assert r.status_code == 204
        listed = (
            await client.get(f"/workspaces/{ws_id}/api-keys", headers=headers)
        ).json()
        assert listed == []


@pytest.mark.asyncio
async def test_dev_auth_shapes_and_scoping():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers_a = await _register(client, f"a{uuid.uuid4().hex[:6]}")
        headers_b = await _register(client, f"b{uuid.uuid4().hex[:6]}")
        ws_a = await _workspace(client, headers_a, "WA")
        ws_b = await _workspace(client, headers_b, "WB")
        agent_a = await _agent(client, headers_a, ws_a)
        agent_b = await _agent(client, headers_b, ws_b)
        created = await _make_key(client, headers_a, ws_a)
        key = created["key"]

        # No key / fake key → flat 401.
        r = await client.post(
            "/api/v1/chat", json={"agent_id": agent_a["id"], "message": "hi"}
        )
        assert r.status_code == 401 and "error" in r.json(), r.text
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": "hi"},
            headers={"X-API-Key": "sk-botbase-" + "0" * 40},
        )
        assert r.status_code == 401 and "error" in r.json(), r.text

        # Foreign-workspace agent → 403 workspace mismatch (no LLM touched).
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_b["id"], "message": "hi"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 403, r.text
        assert "workspace" in r.json()["error"]

        # Inactive agent → 404.
        await client.put(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}",
            json={"is_active": 0},
            headers=headers_a,
        )
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": "hi"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 404, r.text
        await client.put(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}",
            json={"is_active": 1},
            headers=headers_a,
        )

        # Validation → flat 400s (before any auth/LLM work).
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": ""},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 400 and "error" in r.json(), r.text
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": "a" * 4001},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 400 and "error" in r.json(), r.text

        # Restricted key → 403 allowed-list (fails before retrieval).
        restricted = await _make_key(
            client, headers_a, ws_a, allowed_agents=["agent-that-does-not-exist"]
        )
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": "hi"},
            headers={"X-API-Key": restricted["key"]},
        )
        assert r.status_code == 403, r.text
        assert "authorised" in r.json()["error"]

        # Discovery honours the restriction.
        r = await client.get("/api/v1/agents", headers={"X-API-Key": key})
        assert r.status_code == 200
        assert r.json()["workspace_id"] == ws_a
        assert {a["agent_id"] for a in r.json()["agents"]} == {agent_a["id"]}
        r = await client.get(
            "/api/v1/agents", headers={"X-API-Key": restricted["key"]}
        )
        assert r.json()["agents"] == []

        # Revoke → 401 from then on.
        await client.put(
            f"/workspaces/{ws_a}/api-keys/{created['id']}",
            json={"is_active": 0},
            headers=headers_a,
        )
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent_a["id"], "message": "hi"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 401, r.text

        # Cross-owner management → 404.
        r = await client.get(f"/workspaces/{ws_a}/api-keys", headers=headers_b)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_expired_key_rejected():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        created = await _make_key(client, headers, ws_id, expires_at=past)
        r = await client.post(
            "/api/v1/chat",
            json={"agent_id": agent["id"], "message": "hi"},
            headers={"X-API-Key": created["key"]},
        )
        assert r.status_code == 401, r.text


def test_dev_rate_limiter_unit():
    bucket = f"unit-{uuid.uuid4().hex}"
    for _ in range(60):
        assert _check_dev_rate_limit(bucket) == 0
    assert _check_dev_rate_limit(bucket) > 0


def test_dev_error_contract_is_flat():
    """Every developer error body is flat {"error"} — never nested detail."""
    from ..api.developer import _dev_error

    for code in (400, 401, 403, 404, 429, 500):
        resp = _dev_error(code, "msg here", retry_after_seconds=7)
        assert resp.status_code == code
        import json

        body = json.loads(resp.body.decode())
        assert set(body) <= {"error", "retry_after_seconds"}, body
        assert body["error"] == "msg here"
