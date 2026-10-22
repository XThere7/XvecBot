"""
tests/test_data_retention.py (Stage 2)

Data-retention guarantees that a customer expects when they delete a
workspace or a document, plus the proxy-aware rate-limit bucketing that
production (behind Caddy/Vercel) depends on.

  DATA-02  a transcript that quotes a workspace's documents is deleted with it
  DATA-03  deleting a document also deletes the uploaded file
  R5       the rate limiter buckets by the real client IP behind a proxy
"""
import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from ..core.config import settings
from ..core.database import get_db
from ..core.rate_limit import _client_ip
from ..main import app


def _pdf(text: str = "BotBase retention test") -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text)
    data = doc.tobytes()
    doc.close()
    return data


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> dict:
    email = f"retention-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/auth/register", json={"email": email, "password": "pw123456"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _workspace(client: AsyncClient, headers: dict) -> str:
    r = await client.post("/workspaces", json={"name": "retention"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_workspace_delete_removes_workspace_linked_conversation():
    """DATA-02: a transcript linked to the workspace dies with the workspace."""
    async with await _client() as client:
        headers = await _register(client)
        ws = await _workspace(client, headers)

        # Simulate a transcript that quotes the workspace's documents but was
        # not started by an agent (the legacy /api/v1/query shape).
        conv_id = str(uuid.uuid4())
        async with get_db() as db:
            await db.execute(
                "INSERT INTO conversations (id, created_at, workspace_id) VALUES (?, ?, ?)",
                (conv_id, "2026-01-01T00:00:00+00:00", ws),
            )
            await db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, 'user', 'my refund question', '2026-01-01T00:00:00+00:00')",
                (str(uuid.uuid4()), conv_id),
            )
            await db.commit()

        r = await client.delete(f"/workspaces/{ws}", headers=headers)
        assert r.status_code in (200, 204), r.text

        async with get_db() as db:
            async with db.execute(
                "SELECT count(*) AS n FROM conversations WHERE id = ?", (conv_id,)
            ) as cur:
                assert (await cur.fetchone())["n"] == 0, "conversation survived the delete"
            async with db.execute(
                "SELECT count(*) AS n FROM messages WHERE conversation_id = ?", (conv_id,)
            ) as cur:
                assert (await cur.fetchone())["n"] == 0, "messages survived the delete"


@pytest.mark.asyncio
async def test_legacy_document_delete_removes_the_file():
    """DATA-03: deleting a document must delete the bytes on the volume."""
    async with await _client() as client:
        legacy = {"X-API-Key": settings.api_key}
        r = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("retention.pdf", io.BytesIO(_pdf()), "application/pdf")},
            headers=legacy,
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json().get("id") or r.json().get("document_id")
        assert doc_id, r.text

        async with get_db() as db:
            async with db.execute(
                "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
            ) as cur:
                row = await cur.fetchone()
        stored_path = row["file_path"] if row else None
        assert stored_path, "the document row must remember where its bytes live"
        from pathlib import Path

        assert Path(stored_path).exists(), "the uploaded file should exist before the delete"

        r = await client.delete(f"/api/v1/documents/{doc_id}", headers=legacy)
        assert r.status_code in (200, 204), r.text

        assert not Path(stored_path).exists(), "the file must be removed with the document"

        async with get_db() as db:
            async with db.execute(
                "SELECT count(*) AS n FROM documents WHERE id = ?", (doc_id,)
            ) as cur:
                assert (await cur.fetchone())["n"] == 0


@pytest.mark.asyncio
async def test_legacy_transcript_links_to_a_single_workspace():
    """DATA-02: a legacy query quoting one workspace's chunks is attributed."""
    from ..services.query_service import _link_conversation_to_workspace

    async with await _client() as client:
        headers = await _register(client)
        ws = await _workspace(client, headers)

    async with get_db() as db:
        doc_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO documents "
            "(id, filename, upload_date, total_pages, file_size, status) "
            "VALUES (?, ?, ?, ?, ?, 'ready')",
            (doc_id, "policy.pdf", "2026-01-01T00:00:00+00:00", 1, 10),
        )
        await db.execute(
            "INSERT INTO chunks (id, document_id, page, chunk_index, text, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chunk_id, doc_id, 1, 0, "refunds within 14 days", ws),
        )
        await db.execute(
            "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
            (conv_id, "2026-01-01T00:00:00+00:00"),
        )
        await db.commit()

        await _link_conversation_to_workspace(db, conv_id, [{"chunk_id": chunk_id}])

        async with db.execute(
            "SELECT workspace_id FROM conversations WHERE id = ?", (conv_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row["workspace_id"] == ws, "single-tenant transcript must be linked"


@pytest.mark.asyncio
async def test_legacy_transcript_spanning_tenants_stays_global():
    """DATA-02: a transcript quoting several tenants must not be attributed."""
    from ..services.query_service import _link_conversation_to_workspace

    async with await _client() as client:
        headers = await _register(client)
        ws_a = await _workspace(client, headers)
        ws_b = await _workspace(client, headers)

    async with get_db() as db:
        conv_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO documents "
            "(id, filename, upload_date, total_pages, file_size, status) "
            "VALUES (?, ?, ?, ?, ?, 'ready')",
            (doc_id, "shared.pdf", "2026-01-01T00:00:00+00:00", 1, 10),
        )
        chunk_ids = []
        for ws in (ws_a, ws_b):
            chunk_id = str(uuid.uuid4())
            chunk_ids.append(chunk_id)
            await db.execute(
                "INSERT INTO chunks "
                "(id, document_id, page, chunk_index, text, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, doc_id, 1, 0, "tenant text", ws),
            )
        await db.execute(
            "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
            (conv_id, "2026-01-01T00:00:00+00:00"),
        )
        await db.commit()

        await _link_conversation_to_workspace(
            db, conv_id, [{"chunk_id": cid} for cid in chunk_ids]
        )

        async with db.execute(
            "SELECT workspace_id FROM conversations WHERE id = ?", (conv_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row["workspace_id"] is None, "cross-tenant transcript must stay global"


@pytest.mark.asyncio
async def test_rate_limit_buckets_by_forwarded_client_ip():
    """R5: two clients behind one proxy must not share a rate-limit bucket."""
    from starlette.requests import Request

    def _request(forwarded: str | None, client: str = "10.0.0.1") -> Request:
        headers = []
        if forwarded:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/auth/login",
            "headers": headers,
            "client": (client, 1234),
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
        return Request(scope)

    assert _client_ip(_request("203.0.113.7")) == "203.0.113.7"
    assert _client_ip(_request("203.0.113.7, 10.0.0.1")) == "203.0.113.7"
    assert _client_ip(_request(None, "198.51.100.4")) == "198.51.100.4"
