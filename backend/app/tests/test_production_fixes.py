"""
Regression tests for the production-readiness fix set.

Every test uses the isolated temp DB from conftest.py. These cover the
irreversible data-lifecycle paths first, then upload limits/authorization and
the public rate-limit ordering bug.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ..core.config import settings
from ..core.database import get_db
from ..main import app
from ..api import public as public_api
from ..storage import vector_store

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, tag: str) -> dict:
    email = f"prod-{tag}-{uuid.uuid4().hex[:6]}@example.com"
    r = await client.post("/auth/register", json={"email": email, "password": "pw123456"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _workspace(client: AsyncClient, headers: dict, name: str = "ws") -> str:
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _agent(client: AsyncClient, headers: dict, ws_id: str) -> str:
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": "agent", "system_prompt": "Be helpful."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _upload(
    client: AsyncClient,
    headers: dict,
    ws_id: str,
    filename: str = "notes.txt",
    content: bytes = b"hello world",
) -> dict:
    r = await client.post(
        f"/workspaces/{ws_id}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _index_document(db, doc: dict) -> tuple[str, str]:
    """Create the shadow documents row, one chunk, and one vector."""
    chunk_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO documents
           (id, filename, upload_date, total_pages, file_size, status)
           VALUES (?, ?, ?, 1, ?, 'ready')
           ON CONFLICT(id) DO UPDATE SET
               filename=excluded.filename,
               upload_date=excluded.upload_date,
               total_pages=excluded.total_pages,
               file_size=excluded.file_size,
               status=excluded.status""",
        (
            doc["id"],
            doc["filename"],
            doc.get("created_at") or _now(),
            doc.get("size_bytes") or 0,
        ),
    )
    await db.execute(
        """INSERT INTO chunks
           (id, document_id, page, chunk_index, text, workspace_id, doc_id)
           VALUES (?, ?, 1, 0, ?, ?, ?)""",
        (
            chunk_id,
            doc["id"],
            "private workspace text",
            doc["workspace_id"],
            doc["id"],
        ),
    )
    await db.commit()
    await vector_store.insert_embedding(
        db,
        chunk_id,
        [0.0] * settings.embedding_dimension,
        workspace_id=doc["workspace_id"],
        doc_id=doc["id"],
    )
    await db.commit()
    return chunk_id, doc["id"]


@pytest.mark.asyncio
async def test_document_delete_removes_shadow_rows_and_embeddings():
    async with await _client() as client:
        headers = await _register(client, "docdel")
        ws_id = await _workspace(client, headers)
        doc = await _upload(client, headers, ws_id, "delete-me.txt")
        async with get_db() as db:
            chunk_id, doc_id = await _index_document(db, doc)

        r = await client.delete(
            f"/workspaces/{ws_id}/documents/{doc['id']}", headers=headers
        )
        assert r.status_code == 204, r.text

        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(*) AS n FROM workspace_documents WHERE id = ?", (doc["id"],)
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
            async with db.execute(
                "SELECT COUNT(*) AS n FROM documents WHERE id = ?", (doc_id,)
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
            async with db.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE id = ? OR doc_id = ?",
                (chunk_id, doc_id),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
            async with db.execute(
                "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id = ?",
                (chunk_id,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0

        assert not Path(doc["file_path"]).exists()


@pytest.mark.asyncio
async def test_workspace_delete_removes_every_owned_row_and_icon():
    async with await _client() as client:
        headers = await _register(client, "wsdel")
        ws_id = await _workspace(client, headers, "delete-ws")
        doc_a = await _upload(client, headers, ws_id, "same-name.txt", b"a")
        doc_b = await _upload(client, headers, ws_id, "same-name.txt", b"b")
        agent_id = await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent_id}/icon",
            files={"file": ("icon.png", PNG_1X1, "image/png")},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        icon_dir = settings.workspace_upload_path / "icons" / agent_id
        assert icon_dir.is_dir()

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent_id}/conversations/new",
            headers=headers,
        )
        assert r.status_code == 201, r.text
        conv_id = r.json()["id"]

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent_id}/tokens",
            json={"label": "widget", "allowed_origins": []},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        token_id = r.json()["id"]

        r = await client.post(
            f"/workspaces/{ws_id}/api-keys",
            json={"name": "integration"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        key_id = r.json()["id"]

        async with get_db() as db:
            chunk_ids = []
            for doc in (doc_a, doc_b):
                chunk_id, _ = await _index_document(db, doc)
                chunk_ids.append(chunk_id)
            await db.execute(
                """INSERT INTO messages (id, conversation_id, role, content, created_at)
                   VALUES (?, ?, 'user', 'hello', ?)""",
                (str(uuid.uuid4()), conv_id, _now()),
            )
            await db.commit()

        r = await client.delete(f"/workspaces/{ws_id}", headers=headers)
        assert r.status_code == 204, r.text

        async with get_db() as db:
            checks = [
                ("workspaces", "id = ?", ws_id),
                ("workspace_documents", "workspace_id = ?", ws_id),
                ("documents", "id IN (?, ?)", (doc_a["id"], doc_b["id"])),
                ("chunks", "workspace_id = ?", ws_id),
                ("agents", "workspace_id = ?", ws_id),
                ("conversations", "id = ?", conv_id),
                ("messages", "conversation_id = ?", conv_id),
                ("agent_embed_tokens", "id = ?", token_id),
                ("developer_api_keys", "id = ?", key_id),
            ]
            for table, where, value in checks:
                async with db.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", 
                    value if isinstance(value, tuple) else (value,),
                ) as cur:
                    assert (await cur.fetchone())["n"] == 0, table
            for chunk_id in chunk_ids:
                async with db.execute(
                    "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id = ?",
                    (chunk_id,),
                ) as cur:
                    assert (await cur.fetchone())["n"] == 0

        assert not icon_dir.exists()
        assert not (settings.workspace_upload_path / ws_id).exists()


@pytest.mark.asyncio
async def test_delete_by_workspace_does_not_touch_same_filename_in_other_workspace():
    async with await _client() as client:
        headers = await _register(client, "dupe")
        ws_a = await _workspace(client, headers, "A")
        ws_b = await _workspace(client, headers, "B")
        doc_a = await _upload(client, headers, ws_a, "policy.pdf", b"a")
        doc_b = await _upload(client, headers, ws_b, "policy.pdf", b"b")

        async with get_db() as db:
            chunk_a, _ = await _index_document(db, doc_a)
            chunk_b, _ = await _index_document(db, doc_b)
            removed = await vector_store.delete_by_workspace(db, ws_a)
            assert removed == 1

            async with db.execute(
                "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id = ?",
                (chunk_a,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
            async with db.execute(
                "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id = ?",
                (chunk_b,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 1
            async with db.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE id = ?", (chunk_b,)
            ) as cur:
                assert (await cur.fetchone())["n"] == 1


@pytest.mark.asyncio
async def test_direct_upload_enforces_cap_and_removes_partial(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    async with await _client() as client:
        headers = await _register(client, "cap")
        ws_id = await _workspace(client, headers)

        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("big.txt", b"0123456789", "text/plain")},
            headers=headers,
        )
        assert r.status_code == 413, r.text

        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(*) AS n FROM workspace_documents WHERE workspace_id = ?",
                (ws_id,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
        upload_dir = settings.workspace_upload_path / ws_id
        assert not upload_dir.exists() or list(upload_dir.iterdir()) == []

        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("exact.txt", b"12345678", "text/plain")},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["size_bytes"] == 8


@pytest.mark.asyncio
async def test_agent_routes_require_the_workspace_in_the_path():
    async with await _client() as client:
        headers = await _register(client, "agentscope")
        ws_a = await _workspace(client, headers, "A")
        ws_b = await _workspace(client, headers, "B")
        agent_id = await _agent(client, headers, ws_a)

        r = await client.get(f"/workspaces/{ws_b}/agents/{agent_id}", headers=headers)
        assert r.status_code == 404, r.text
        r = await client.put(
            f"/workspaces/{ws_b}/agents/{agent_id}",
            json={"name": "hijacked"},
            headers=headers,
        )
        assert r.status_code == 404, r.text
        r = await client.delete(f"/workspaces/{ws_b}/agents/{agent_id}", headers=headers)
        assert r.status_code == 404, r.text

        r = await client.get(f"/workspaces/{ws_a}/agents/{agent_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "agent"


@pytest.mark.asyncio
async def test_legacy_documents_list_accepts_no_trailing_slash(test_client):
    r = await test_client.get("/api/v1/documents")
    assert r.status_code == 200, r.text
    assert "documents" in r.json()
    r = await test_client.get("/api/v1/documents/")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_blocked_origin_does_not_consume_public_rate_limit():
    async with await _client() as client:
        headers = await _register(client, "ratelimit")
        ws_id = await _workspace(client, headers)
        agent_id = await _agent(client, headers, ws_id)
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent_id}/tokens",
            json={"label": "restricted", "allowed_origins": ["shop.example.com"]},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        token = r.json()["token"]

        fake_result = {
            "answer": "ok",
            "sources": [],
            "conversation_id": str(uuid.uuid4()),
        }
        with patch.object(
            public_api.embed_service,
            "chat_for_public_agent",
            new=AsyncMock(return_value=fake_result),
        ):
            # More than RATE_LIMIT_MAX blocked requests: all must stay 403, not
            # become 429, and none may consume the legitimate bucket.
            for _ in range(25):
                r = await client.post(
                    "/public/chat",
                    json={"token": token, "message": "hello"},
                    headers={"Origin": "https://evil.example"},
                )
                assert r.status_code == 403, r.text

            r = await client.post(
                "/public/chat",
                json={"token": token, "message": "hello"},
                headers={"Origin": "https://shop.example.com"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["answer"] == "ok"

        async with get_db() as db:
            async with db.execute(
                "SELECT request_count FROM agent_embed_tokens WHERE token = ?",
                (token,),
            ) as cur:
                assert (await cur.fetchone())["request_count"] == 1
