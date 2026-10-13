"""
tests/test_agent_icon.py — bot avatar upload (Task 2).

Covers the prompt's 9 icon checks: upload returns icon_url, file served 200,
public info carries absolute icon_url, delete NULLs it (widget falls back),
oversize and non-image 400s, plus ownership gating and replace-cleanup.
Runs on the isolated temp DB (conftest) — never touches dev data.
"""
import io
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..main import app

# Minimal valid 1x1 PNG (magic bytes + IHDR/IEND) — passes the signature gate.
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _register(client, tag):
    email = f"icon-{tag}@example.com"
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
        json={"name": name, "system_prompt": "Be helpful."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _icon_url(client, headers, ws_id, agent_id):
    return f"/workspaces/{ws_id}/agents/{agent_id}/icon"


@pytest.mark.asyncio
async def test_icon_upload_sets_url_and_serves_bytes():
    """Checks 2+3: upload returns icon_url; GET on the served path is 200."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        url = _icon_url(client, headers, ws_id, agent["id"])

        r = await client.post(
            url,
            files={"file": ("avatar.png", io.BytesIO(PNG_1X1), "image/png")},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["icon_url"] is not None
        assert body["icon_url"].startswith(f"/static/icons/{agent['id']}/")

        r = await client.get(body["icon_url"])
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.content == PNG_1X1


@pytest.mark.asyncio
async def test_icon_replace_deletes_old_file():
    """Re-upload swaps the file on disk — no orphans accumulate."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        url = _icon_url(client, headers, ws_id, agent["id"])

        first = (
            await client.post(
                url,
                files={"file": ("a.png", io.BytesIO(PNG_1X1), "image/png")},
                headers=headers,
            )
        ).json()["icon_url"]
        second = (
            await client.post(
                url,
                files={"file": ("b.png", io.BytesIO(PNG_1X1), "image/png")},
                headers=headers,
            )
        ).json()["icon_url"]
        assert first != second
        assert (await client.get(first)).status_code == 404
        assert (await client.get(second)).status_code == 200


@pytest.mark.asyncio
async def test_icon_delete_nulls_and_unserves():
    """Checks 6+7: DELETE returns icon_url null; file no longer served."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        url = _icon_url(client, headers, ws_id, agent["id"])

        icon = (
            await client.post(
                url,
                files={"file": ("a.png", io.BytesIO(PNG_1X1), "image/png")},
                headers=headers,
            )
        ).json()["icon_url"]

        r = await client.delete(url, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["icon_url"] is None
        assert (await client.get(icon)).status_code == 404


@pytest.mark.asyncio
async def test_icon_public_info_absolute_and_null():
    """Check 4: /public/agent/{token} carries absolute icon_url, then null."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        url = _icon_url(client, headers, ws_id, agent["id"])

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/tokens",
            json={"label": "widget"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        token = r.json()["token"]

        info = (
            await client.get(f"/public/agent/{token}")
        ).json()
        assert info["icon_url"] is None

        await client.post(
            url,
            files={"file": ("a.png", io.BytesIO(PNG_1X1), "image/png")},
            headers=headers,
        )
        info = (
            await client.get(f"/public/agent/{token}")
        ).json()
        assert info["icon_url"] is not None
        assert info["icon_url"].startswith("http")
        assert "/static/icons/" in info["icon_url"]
        assert ".." not in info["icon_url"]

        await client.delete(url, headers=headers)
        info = (
            await client.get(f"/public/agent/{token}")
        ).json()
        assert info["icon_url"] is None


@pytest.mark.asyncio
async def test_icon_rejects_oversize():
    """Check 8: > 2 MB is 400 with the exact message."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024)
        r = await client.post(
            _icon_url(client, headers, ws_id, agent["id"]),
            files={"file": ("big.png", io.BytesIO(big), "image/png")},
            headers=headers,
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Image must be under 2 MB."


@pytest.mark.asyncio
async def test_icon_rejects_non_image():
    """Check 9: a PDF (by ext and by magic bytes) is 400 with the message."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        url = _icon_url(client, headers, ws_id, agent["id"])

        r = await client.post(
            url,
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            headers=headers,
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Only PNG, JPG, WebP, and GIF images are allowed."

        # Renamed payload: .png name, PDF bytes — magic-byte gate catches it.
        r = await client.post(
            url,
            files={"file": ("evil.png", io.BytesIO(b"%PDF-1.4 fake"), "image/png")},
            headers=headers,
        )
        assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_icon_endpoints_enforce_ownership():
    """Another user's agent icon routes are 404, never 200."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        owner = await _register(client, uuid.uuid4().hex[:8])
        stranger = await _register(client, uuid.uuid4().hex[:8])
        ws_id = await _workspace(client, owner)
        agent = await _agent(client, owner, ws_id)
        url = _icon_url(client, owner, ws_id, agent["id"])

        r = await client.post(
            url,
            files={"file": ("a.png", io.BytesIO(PNG_1X1), "image/png")},
            headers=stranger,
        )
        assert r.status_code == 404, r.text
        r = await client.delete(url, headers=stranger)
        assert r.status_code == 404, r.text
        # Owner's agent untouched.
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}", headers=owner
        )
        assert r.json()["icon_url"] is None
