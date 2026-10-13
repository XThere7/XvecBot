"""
tests/test_storage_presigned.py (Phase 2)
Object-storage backends (local + mocked S3 via moto) and the presigned
upload endpoints. No network, no real credentials, no dev-DB pollution risk
beyond the shared SQLite file (rows use unique workspace ids per test).
"""
import io
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..core.config import settings
from ..main import app
from ..storage.object_store import (
    LocalBackend,
    S3Backend,
    build_object_key,
    content_type_for,
    get_storage,
    reset_storage_cache,
)


def test_content_type_mapping():
    assert content_type_for("a.pdf") == "application/pdf"
    assert content_type_for("a.TXT") == "text/plain"
    assert content_type_for("a.docx").startswith("application/vnd")
    assert content_type_for("a.bin") == "application/octet-stream"


def test_build_object_key_no_traversal():
    key = build_object_key("ws1", "doc1", "../../etc/passwd", "botbase")
    assert key == "botbase/workspaces/ws1/doc1_passwd"
    assert ".." not in key
    assert not key.startswith("/")


def test_local_backend_roundtrip(tmp_path):
    backend = LocalBackend(tmp_path)
    backend.put_object("workspaces/ws1/doc1_f.txt", b"hello", "text/plain")
    head = backend.head_object("workspaces/ws1/doc1_f.txt")
    assert head is not None and head.size_bytes == 5
    assert backend.get_object("workspaces/ws1/doc1_f.txt") == b"hello"
    assert backend.head_object("missing") is None
    assert backend.delete_prefix("workspaces/ws1") == 1
    assert backend.head_object("workspaces/ws1/doc1_f.txt") is None
    with pytest.raises(NotImplementedError):
        backend.presigned_put("k")


def _moto_s3():
    from moto import mock_aws

    mock = mock_aws()
    mock.start()
    import boto3

    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    return mock, client


def test_s3_backend_roundtrip_monkeypatched(monkeypatch):
    mock, _ = _moto_s3()
    try:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
        backend = S3Backend(bucket="test-bucket", region="us-east-1")
        backend.put_object("a/b.txt", b"data123", "text/plain")
        head = backend.head_object("a/b.txt")
        assert head is not None and head.size_bytes == 7
        assert backend.get_object("a/b.txt") == b"data123"
        put_url = backend.presigned_put("a/b.txt", "text/plain", 60)
        assert put_url.startswith("https://")
        get_url = backend.presigned_get("a/b.txt", 60)
        assert "a/b.txt" in get_url
        assert backend.delete_prefix("a") == 1
        assert backend.head_object("a/b.txt") is None
    finally:
        mock.stop()


def _auth_headers():
    return {"X-API-Key": settings.api_key}


async def _register_user_and_workspace(client, suffix):
    email = f"phase2-{suffix}@example.com"
    resp = await client.post(
        "/auth/register", json={"email": email, "password": "pw123456"}
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ws = await client.post("/workspaces", json={"name": f"ws-{suffix}"}, headers=headers)
    assert ws.status_code == 201, ws.text
    return headers, ws.json()["id"]


@pytest.mark.asyncio
async def test_presigned_endpoints_need_storage():
    """Without S3_BUCKET the presigned routes must 501, legacy flow unaffected."""
    reset_storage_cache()
    assert settings.use_s3_storage is False
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers, ws_id = await _register_user_and_workspace(client, uuid.uuid4().hex[:8])
        r = await client.post(
            f"/workspaces/{ws_id}/documents/upload-url",
            json={"filename": "doc.pdf"},
            headers=headers,
        )
        assert r.status_code == 501, r.text
        r = await client.get(
            f"/workspaces/{ws_id}/documents/none/download-url", headers=headers
        )
        assert r.status_code in (400, 404, 501), r.text


@pytest.mark.asyncio
async def test_presigned_full_flow_with_moto(monkeypatch):
    """upload-url -> PUT bytes to mocked S3 -> complete-upload -> download-url."""
    mock, _ = _moto_s3()
    try:
        monkeypatch.setattr(settings, "s3_bucket", "test-bucket")
        monkeypatch.setattr(settings, "s3_prefix", "t2")
        monkeypatch.setattr(settings, "s3_endpoint_url", "")
        monkeypatch.setattr(settings, "s3_region", "us-east-1")
        monkeypatch.setattr(settings, "storage_backend", "auto")
        reset_storage_cache()
        assert isinstance(get_storage(), S3Backend)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers, ws_id = await _register_user_and_workspace(
                client, uuid.uuid4().hex[:8]
            )
            r = await client.post(
                f"/workspaces/{ws_id}/documents/upload-url",
                json={"filename": "notes.txt"},
                headers=headers,
            )
            assert r.status_code == 201, r.text
            body = r.json()
            doc_id = body["doc_id"]
            assert body["method"] == "presigned-put"
            assert body["object_key"].startswith("t2/workspaces/")

            # complete before PUT must 400 (nothing in storage yet)
            r = await client.post(
                f"/workspaces/{ws_id}/documents/{doc_id}/complete-upload",
                headers=headers,
            )
            assert r.status_code == 400, r.text

            # PUT bytes straight to mocked S3 (what the browser would do)
            backend = get_storage()
            import asyncio

            await asyncio.to_thread(
                backend.put_object, body["object_key"], b"hello phase2", "text/plain"
            )

            r = await client.post(
                f"/workspaces/{ws_id}/documents/{doc_id}/complete-upload",
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "uploaded"
            assert r.json()["size_bytes"] == 12

            r = await client.get(
                f"/workspaces/{ws_id}/documents/{doc_id}/download-url",
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["method"] == "presigned-get"

            # invalid extension rejected at mint time
            r = await client.post(
                f"/workspaces/{ws_id}/documents/upload-url",
                json={"filename": "evil.exe"},
                headers=headers,
            )
            assert r.status_code == 400, r.text
    finally:
        reset_storage_cache()
        mock.stop()


@pytest.mark.asyncio
async def test_legacy_upload_still_works_without_storage(tmp_path):
    """Legacy direct upload path is untouched by Phase 2 (local disk)."""
    reset_storage_cache()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers, ws_id = await _register_user_and_workspace(
            client, uuid.uuid4().hex[:8]
        )
        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("doc.txt", io.BytesIO(b"legacy bytes"), "text/plain")},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "uploaded"
        assert r.json().get("object_key") in (None, "")
