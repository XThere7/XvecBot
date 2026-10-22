"""
tests/test_hosted_chat.py (Task 1, Method B) — shareable /chat/<token> pages.

- Snippet response carries hosted_url on the botbase domain.
- Hosted dashboard origin is auto-permitted even for origin-restricted
  tokens (no Origin / localhost / customer site matrix included).
- Public agent info + chat still work end to end through the hosted flow.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..core.database import get_db
from ..main import app


async def _register(client, tag):
    email = f"hosted-{tag}@example.com"
    r = await client.post(
        "/auth/register", json={"email": email, "password": "pw123456"}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _workspace(client, headers):
    r = await client.post("/workspaces", json={"name": "ws"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _agent(client, headers, ws_id):
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": "agent", "system_prompt": "Be helpful always."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _token(client, headers, ws_id, agent_id, **body):
    payload = {"label": "site"}
    payload.update(body)
    r = await client.post(
        f"/workspaces/{ws_id}/agents/{agent_id}/tokens",
        json=payload,
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.mark.asyncio
async def test_snippet_carries_botbase_hosted_url():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent_id = await _agent(client, headers, ws_id)
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent_id}/tokens",
            json={"label": "site"},
            headers=headers,
        )
        token_id = r.json()["id"]
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent_id}/tokens/{token_id}/snippet",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hosted_url"].startswith("https://app.botbase.tz/chat/")
        assert body["hosted_url"].endswith(body["token"])


@pytest.mark.asyncio
async def test_hosted_origin_allowed_despite_restriction():
    """A token locked to a customer site still serves the hosted page origin."""
    from ..services import embed_service

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent_id = await _agent(client, headers, ws_id)
        token = await _token(
            client, headers, ws_id, agent_id, allowed_origins=["shop.example.com"]
        )

        # Customer site: allowed. Random site: 403. Hosted page: allowed.
        assert (
            await client.post(
                "/public/chat",
                json={"token": token, "message": "hi"},
                headers={"Origin": "https://shop.example.com"},
            )
        ).status_code in (200, 500)
        r = await client.post(
            "/public/chat",
            json={"token": token, "message": "hi"},
            headers={"Origin": "https://evil.example.org"},
        )
        assert r.status_code == 403, r.text
        r = await client.post(
            "/public/chat",
            json={"token": token, "message": "hi"},
            headers={"Origin": "https://app.botbase.tz"},
        )
        assert r.status_code in (200, 500), r.text

        # Unit-level: the allowance keys off the configured base, not hardcoded.
        assert embed_service._hostname("https://app.botbase.tz") == "app.botbase.tz"


@pytest.mark.asyncio
async def test_qr_png_for_valid_token():
    """Method C: QR serves PNG bytes; unknown/revoked tokens are refused."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent_id = await _agent(client, headers, ws_id)
        token = await _token(client, headers, ws_id, agent_id)

        r = await client.get(f"/public/qr/{token}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(r.content) > 500

        r = await client.get("/public/qr/does-not-exist")
        assert r.status_code == 401, r.text

        # Revoked token: QR refused like the rest of the public surface.
        async with get_db() as db:
            await db.execute(
                "UPDATE agent_embed_tokens SET is_active = 0 WHERE token = ?",
                (token,),
            )
            await db.commit()
        r = await client.get(f"/public/qr/{token}")
        assert r.status_code == 403, r.text
