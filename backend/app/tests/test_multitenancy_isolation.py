"""
tests/test_multitenancy_isolation.py — Task 1 audit proof (the fixed gap).

Covers the 10-step isolation sequence at the layer that was actually broken:
conversation ids were accepted without checking they belong to the agent in
the path, so any user could read/delete ANY conversation via their own agent.
chat_with_agent() already bound them (foreign id → 404); GET/DELETE did not.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..main import app


async def _register(client, tag):
    email = f"iso-{tag}@example.com"
    r = await client.post(
        "/auth/register", json={"email": email, "password": "pw123456"}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _workspace(client, headers, name="ws"):
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _agent(client, headers, ws_id):
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": "agent", "system_prompt": "Be helpful."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _conversation(client, headers, ws_id, agent_id):
    r = await client.post(
        f"/workspaces/{ws_id}/agents/{agent_id}/conversations/new",
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_cross_user_conversation_cannot_be_read():
    """User B reads A's conversation through B's own agent → 404, not data."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers_a = await _register(client, f"a{uuid.uuid4().hex[:6]}")
        headers_b = await _register(client, f"b{uuid.uuid4().hex[:6]}")
        ws_a = await _workspace(client, headers_a, "WA")
        ws_b = await _workspace(client, headers_b, "WB")
        agent_a = await _agent(client, headers_a, ws_a)
        agent_b = await _agent(client, headers_b, ws_b)
        conv_a = await _conversation(client, headers_a, ws_a, agent_a)

        # Step 5/10 analogues: foreign workspace / agent / conversation → 404.
        r = await client.get(f"/workspaces/{ws_a}", headers=headers_b)
        assert r.status_code == 404, r.text
        r = await client.get(
            f"/workspaces/{ws_b}/agents/{agent_b}/conversations/{conv_a}",
            headers=headers_b,
        )
        assert r.status_code == 404, r.text
        body = r.json()
        assert "messages" not in body

        # Owner can still read their own.
        r = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a}/conversations/{conv_a}",
            headers=headers_a,
        )
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_cross_user_conversation_cannot_be_deleted():
    """User B deletes A's conversation through B's own agent → 404, row kept."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers_a = await _register(client, f"a{uuid.uuid4().hex[:6]}")
        headers_b = await _register(client, f"b{uuid.uuid4().hex[:6]}")
        ws_a = await _workspace(client, headers_a, "WA")
        ws_b = await _workspace(client, headers_b, "WB")
        agent_a = await _agent(client, headers_a, ws_a)
        agent_b = await _agent(client, headers_b, ws_b)
        conv_a = await _conversation(client, headers_a, ws_a, agent_a)

        r = await client.delete(
            f"/workspaces/{ws_b}/agents/{agent_b}/conversations/{conv_a}",
            headers=headers_b,
        )
        assert r.status_code == 404, r.text

        # A's conversation survived.
        r = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a}/conversations/{conv_a}",
            headers=headers_a,
        )
        assert r.status_code == 200, r.text

        # Same-owner, wrong-workspace path is also rejected.
        ws_a2 = await _workspace(client, headers_a, "WA2")
        agent_a2 = await _agent(client, headers_a, ws_a2)
        r = await client.get(
            f"/workspaces/{ws_a2}/agents/{agent_a2}/conversations/{conv_a}",
            headers=headers_a,
        )
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_cross_user_agent_access_forbidden():
    """Foreign agent rows are 404 (never 403, never leaked)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers_a = await _register(client, f"a{uuid.uuid4().hex[:6]}")
        headers_b = await _register(client, f"b{uuid.uuid4().hex[:6]}")
        ws_a = await _workspace(client, headers_a, "WA")
        ws_b = await _workspace(client, headers_b, "WB")
        agent_a = await _agent(client, headers_a, ws_a)

        r = await client.get(
            f"/workspaces/{ws_b}/agents/{agent_a}", headers=headers_b
        )
        assert r.status_code == 404, r.text
        assert "system_prompt" not in r.text
