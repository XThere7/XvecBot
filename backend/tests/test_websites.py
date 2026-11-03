"""Focused Website-to-Knowledge tests.

The crawler is faked so these tests never depend on the public internet or on
the embedding model. The pipeline below the crawler is real: the app's tables,
chunker, indexer, SQLite vector store, citation metadata, and delete paths are
all exercised.
"""
import asyncio
import uuid
from typing import Optional

import httpx
import pytest
from fastapi import HTTPException

from app.core import ssrf_guard
from app.core.config import settings
from app.core.database import get_db
from app.services import plan_service, website_crawler, website_training_service
from app.services.workspace_query_service import (
    _build_sources,
    _source_metadata_for_chunks,
)
from app.storage import sqlite as db_ops
from app.services.website_crawler import CrawlError, extract_text

PAGE_TEXT = (
    "Example Domain. This page explains the example documentation and the "
    "services described by the example organisation. It contains enough "
    "useful prose for the crawler's minimum text threshold. "
) * 3


async def _register(client) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"web-{uuid.uuid4().hex[:12]}@example.com",
            "password": "pw123456",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _workspace(client, headers: dict) -> str:
    response = await client.post(
        "/workspaces",
        json={"name": f"Website {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _free_workspace(client, headers: dict) -> str:
    """Create a workspace and remove the registration trial for Free gates."""
    workspace_id = await _workspace(client, headers)
    async with get_db() as db:
        await plan_service.set_workspace_plan(db, workspace_id, "free")
        await db.execute(
            "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = (SELECT owner_id FROM workspaces WHERE id = ?)",
            (workspace_id,),
        )
        await db.commit()
    return workspace_id


def _install_fakes(
    monkeypatch,
    text: str = PAGE_TEXT,
    pages: Optional[list[str]] = None,
) -> dict:
    state = {
        "pages": list(pages) if pages is not None else ["https://example.com/"],
        "texts": {},
        "titles": {},
        "fail": set(),
        "fetches": 0,
    }
    for page_url in state["pages"]:
        state["texts"][page_url] = text

    async def fake_validate(url: str, *, resolve_dns: bool = True) -> str:
        return url

    async def fake_discover(root_url: str, *, max_pages: int = 50, session=None):
        return list(state["pages"])

    async def fake_fetch(url: str, *, session):
        state["fetches"] += 1
        if url in state["fail"]:
            raise CrawlError("Page returned HTTP 500.")
        if url not in state["texts"]:
            raise CrawlError("Page returned HTTP 404.")
        title = state["titles"].get(url, "Example Domain")
        return url, title, state["texts"][url]

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * settings.embedding_dimension for _ in texts]

    monkeypatch.setattr(ssrf_guard, "validate_url_async", fake_validate)
    monkeypatch.setattr(website_crawler, "discover_pages", fake_discover)
    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch)
    monkeypatch.setattr(website_crawler, "REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(website_training_service, "embed_texts", fake_embed)
    return state


async def _wait_for_sync(client, headers: dict, workspace_id: str, source_id: str):
    for _ in range(80):
        response = await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        source = response.json()
        if source["status"] in ("synced", "failed"):
            return source
        await asyncio.sleep(0.05)
    raise AssertionError("website sync did not finish in time")


def test_ssrf_guard_blocks_private_targets_and_bad_schemes():
    blocked = [
        "http://127.0.0.1/",
        "http://127.0.0.1:8000/admin",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/",
        "http://192.168.1.5/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com/",
        "http://example.com\\@127.0.0.1/",
    ]
    for url in blocked:
        with pytest.raises(HTTPException) as exc:
            ssrf_guard.validate_url(url)
        assert exc.value.status_code == 400
        # The rejection must never echo an internal address back to the caller.
        assert "127.0.0.1" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_crawler_allows_www_redirects_but_rejects_cross_site_redirects(
    monkeypatch,
):
    async def fake_validate(url: str, *, resolve_dns: bool = True) -> str:
        return url

    async def fake_safe_follow(url: str) -> str:
        return url

    monkeypatch.setattr(ssrf_guard, "validate_url_async", fake_validate)
    monkeypatch.setattr(ssrf_guard, "safe_follow_redirect", fake_safe_follow)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": "https://www.example.com/final"}
            )
        if request.url.path == "/evil":
            return httpx.Response(
                302, headers={"location": "https://evil.example.net/phish"}
            )
        return httpx.Response(200, text="<html><body>ok</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, follow_redirects=False, trust_env=False
    ) as session:
        final_url, _, body = await website_crawler._get_bytes_once(
            "https://example.com/start", session=session
        )
        assert final_url == "https://www.example.com/final"
        assert body == b"<html><body>ok</body></html>"

        with pytest.raises(CrawlError, match="different site"):
            await website_crawler._get_bytes_once(
                "https://example.com/evil", session=session
            )


def test_extract_text_removes_navigation_scripts_and_short_pages():
    html = """
    <html><head><title>Acme Documentation</title></head><body>
      <nav>Navigation that must disappear</nav>
      <script>alert('no')</script>
      <header>Site header</header>
      <main><h1>Acme Documentation</h1>
        <p>Useful documentation content for the Acme product.</p>
        <p>This paragraph is long enough to make the page indexable and
        useful to a customer asking a question about the product.</p>
      </main>
      <footer>Copyright footer</footer>
    </body></html>
    """
    title, text = extract_text(html, "https://example.com/docs")
    assert title == "Acme Documentation"
    assert "Navigation that must disappear" not in text
    assert "Copyright footer" not in text
    assert "alert('no')" not in text
    assert len(text) >= 100

    with pytest.raises(CrawlError):
        extract_text("<html><body><p>too short</p></body></html>", "https://example.com")


@pytest.mark.asyncio
async def test_website_sync_indexes_pages_and_citations(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)

    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    source_id = created.json()["id"]
    assert created.json()["status"] in ("pending", "syncing")

    source = await _wait_for_sync(client, headers, workspace_id, source_id)
    assert source["status"] == "synced", source
    assert source["pages_discovered"] == 1
    assert source["pages_indexed"] == 1

    pages_response = await client.get(
        f"/workspaces/{workspace_id}/websites/{source_id}/pages",
        headers=headers,
    )
    assert pages_response.status_code == 200
    pages = pages_response.json()
    assert len(pages) == 1
    assert pages[0]["status"] == "indexed"
    assert pages[0]["chunk_count"] > 0
    assert pages[0]["url"] == "https://example.com/"

    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM chunks WHERE workspace_id = ? AND doc_id = ?",
            (workspace_id, pages[0]["id"]),
        ) as cur:
            chunk_ids = [row["id"] for row in await cur.fetchall()]
        assert chunk_ids
        chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)
        metadata = await _source_metadata_for_chunks(db, chunks)
        sources = _build_sources(chunks, metadata)
        assert sources[0]["source_url"] == "https://example.com/"

        async with db.execute(
            "SELECT status, file_type FROM workspace_documents WHERE id = ?",
            (pages[0]["id"],),
        ) as cur:
            shadow = await cur.fetchone()
        assert shadow["status"] == "ready"
        assert shadow["file_type"] == "website"

        async with db.execute(
            "SELECT status FROM documents WHERE id = ?", (pages[0]["id"],)
        ) as cur:
            legacy_shadow = await cur.fetchone()
        assert legacy_shadow["status"] == "ready"

    # Website shadow documents are internal: the legacy/global document API
    # and the normal workspace document APIs must not expose or delete them.
    page_id = pages[0]["id"]
    legacy_api_headers = {"X-API-Key": settings.api_key}
    legacy_list = await client.get("/api/v1/documents/", headers=legacy_api_headers)
    assert legacy_list.status_code == 200
    assert page_id not in {doc["id"] for doc in legacy_list.json()["documents"]}
    legacy_detail = await client.get(
        f"/api/v1/documents/{page_id}", headers=legacy_api_headers
    )
    assert legacy_detail.status_code == 404
    legacy_delete = await client.delete(
        f"/api/v1/documents/{page_id}", headers=legacy_api_headers
    )
    assert legacy_delete.status_code == 404
    workspace_status = await client.get(
        f"/workspaces/{workspace_id}/documents/{page_id}/status", headers=headers
    )
    assert workspace_status.status_code == 404
    workspace_delete = await client.delete(
        f"/workspaces/{workspace_id}/documents/{page_id}", headers=headers
    )
    assert workspace_delete.status_code == 404

    # A second sync with identical content reuses the index rather than
    # writing duplicate chunks.
    await website_training_service.sync_website_source(
        source_id, triggered_by="manual"
    )
    history = await client.get(
        f"/workspaces/{workspace_id}/websites/{source_id}/history",
        headers=headers,
    )
    assert history.status_code == 200
    jobs = history.json()
    assert len(jobs) >= 2
    assert jobs[0]["status"] == "completed", jobs
    assert jobs[0]["pages_unchanged"] == 1, jobs
    assert jobs[0]["pages_indexed"] == 0, jobs
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE workspace_id = ? AND doc_id = ?",
            (workspace_id, pages[0]["id"]),
        ) as cur:
            row = await cur.fetchone()
        assert row["n"] == len(chunk_ids)

    refreshed = await client.post(
        f"/workspaces/{workspace_id}/websites/{source_id}/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 202, refreshed.text
    refreshed_source = await _wait_for_sync(client, headers, workspace_id, source_id)
    assert refreshed_source["status"] == "synced"

    duplicate = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    other_headers = await _register(client)
    foreign = await client.get(
        f"/workspaces/{workspace_id}/websites/{source_id}",
        headers=other_headers,
    )
    assert foreign.status_code == 404

    deleted = await client.delete(
        f"/workspaces/{workspace_id}/websites/{source_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 0
        async with db.execute(
            "SELECT COUNT(*) AS n FROM workspace_documents WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 0
        async with db.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE id = ?", (pages[0]["id"],)
        ) as cur:
            assert (await cur.fetchone())["n"] == 0

    missing = await client.get(
        f"/workspaces/{workspace_id}/websites/{source_id}", headers=headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_changed_page_replaces_its_chunks(client, monkeypatch):
    state = _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)
    pages = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    page_id = pages[0]["id"]

    replaced = (
        "Completely rewritten guidance. This replacement page describes a "
        "different policy and contains enough useful text to be indexed. "
    ) * 3
    state["texts"]["https://example.com/"] = replaced
    await website_training_service.sync_website_source(
        source_id, triggered_by="manual"
    )

    pages = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    assert pages[0]["status"] == "indexed"
    assert pages[0]["chunk_count"] > 0

    async with get_db() as db:
        async with db.execute(
            "SELECT text FROM chunks WHERE workspace_id = ? AND doc_id = ?",
            (workspace_id, page_id),
        ) as cur:
            chunk_text = "\n".join(row["text"] for row in await cur.fetchall())
    assert "Completely rewritten guidance" in chunk_text
    assert "Example Domain" not in chunk_text

    history = await client.get(
        f"/workspaces/{workspace_id}/websites/{source_id}/history",
        headers=headers,
    )
    assert history.json()[0]["pages_indexed"] == 1
    assert history.json()[0]["pages_unchanged"] == 0


@pytest.mark.asyncio
async def test_removed_page_is_marked_and_dropped(client, monkeypatch):
    state = _install_fakes(
        monkeypatch,
        pages=["https://example.com/", "https://example.com/old"],
    )
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    pages = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    assert len(pages) == 2
    old_page = next(page for page in pages if page["url"].endswith("/old"))

    state["pages"] = ["https://example.com/"]
    await website_training_service.sync_website_source(
        source_id, triggered_by="manual"
    )

    pages = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    old_page = next(page for page in pages if page["id"] == old_page["id"])
    assert old_page["status"] == "removed"
    assert old_page["chunk_count"] == 0

    source = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}",
            headers=headers,
        )
    ).json()
    assert source["status"] == "synced"
    assert source["pages_indexed"] == 1

    async with get_db() as db:
        for table, column in (
            ("chunks", "doc_id"),
            ("workspace_documents", "id"),
            ("documents", "id"),
        ):
            async with db.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?",
                (old_page["id"],),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0, table


@pytest.mark.asyncio
async def test_failed_page_drops_stale_chunks_and_recovers(client, monkeypatch):
    state = _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/", "refresh_policy": "daily"},
        headers=headers,
    )
    source_id = created.json()["id"]
    initial_source = await _wait_for_sync(client, headers, workspace_id, source_id)
    initial_last_synced = initial_source["last_synced_at"]
    assert initial_last_synced
    pages = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    page_id = pages[0]["id"]

    state["fail"].add("https://example.com/")
    await website_training_service.sync_website_source(
        source_id, triggered_by="manual"
    )

    source = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}",
            headers=headers,
        )
    ).json()
    assert source["status"] == "failed"
    # A failed sync must not look like a successful refresh or reset the
    # manual-refresh cooldown clock.
    assert source["last_synced_at"] == initial_last_synced
    assert source["next_sync_at"]
    failed_page = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()[0]
    assert failed_page["status"] == "failed"
    assert failed_page["chunk_count"] == 0

    async with get_db() as db:
        for table, column in (
            ("chunks", "doc_id"),
            ("workspace_documents", "id"),
            ("documents", "id"),
        ):
            async with db.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?",
                (page_id,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0, table

    state["fail"].clear()
    await website_training_service.sync_website_source(
        source_id, triggered_by="manual"
    )
    recovered = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}", headers=headers
        )
    ).json()
    assert recovered["status"] == "synced"
    recovered_page = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()[0]
    assert recovered_page["status"] == "indexed"
    assert recovered_page["chunk_count"] > 0


@pytest.mark.asyncio
async def test_source_is_hard_capped_at_fifty_pages(client, monkeypatch):
    pages = ["https://example.com/"] + [
        f"https://example.com/page-{index}" for index in range(54)
    ]
    _install_fakes(monkeypatch, pages=pages)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    source = await _wait_for_sync(client, headers, workspace_id, source_id)
    assert source["status"] == "synced"
    assert source["pages_discovered"] == 50
    assert source["pages_indexed"] == 50
    listed = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/pages",
            headers=headers,
        )
    ).json()
    assert len(listed) == 50

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT doc_id) AS n FROM chunks WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 50
        async with db.execute(
            """SELECT COUNT(*) AS n FROM workspace_documents
               WHERE workspace_id = ? AND file_type = 'website'""",
            (workspace_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 50


@pytest.mark.asyncio
async def test_concurrent_syncs_only_one_claim_wins(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    original_fetch = website_crawler.fetch_page

    async def slow_fetch(url: str, *, session):
        await asyncio.sleep(0.2)
        return await original_fetch(url, session=session)

    monkeypatch.setattr(website_crawler, "fetch_page", slow_fetch)
    first, second = await asyncio.gather(
        website_training_service.sync_website_source(
            source_id, triggered_by="manual"
        ),
        website_training_service.sync_website_source(
            source_id, triggered_by="manual"
        ),
    )
    assert sum(bool(result.get("skipped")) for result in (first, second)) == 1
    completed = first if not first.get("skipped") else second
    assert completed["pages_unchanged"] == 1

    history = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/history",
            headers=headers,
        )
    ).json()
    new_jobs = [job for job in history if job["finished_at"]]
    assert len(new_jobs) == 2  # initial sync + exactly one of the two calls
    assert new_jobs[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_interrupted_sync_is_recovered(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    # Simulate a process exit while the crawl was in flight.
    async with get_db() as db:
        await db.execute(
            "UPDATE website_sources SET status = 'syncing' WHERE id = ?",
            (source_id,),
        )
        await db.execute(
            """UPDATE website_sync_jobs
               SET status = 'running', finished_at = NULL
               WHERE source_id = ?""",
            (source_id,),
        )
        await db.commit()

    recovered = await website_training_service.recover_stale_syncs()
    assert recovered >= 1

    source = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}", headers=headers
        )
    ).json()
    assert source["status"] == "failed"
    assert "interrupted" in (source["error_message"] or "").lower()
    history = (
        await client.get(
            f"/workspaces/{workspace_id}/websites/{source_id}/history",
            headers=headers,
        )
    ).json()
    assert history[0]["status"] == "failed"

    # The source is no longer stuck: a manual refresh can claim it again.
    refreshed = await client.post(
        f"/workspaces/{workspace_id}/websites/{source_id}/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 202, refreshed.text
    source = await _wait_for_sync(client, headers, workspace_id, source_id)
    assert source["status"] == "synced"


@pytest.mark.asyncio
async def test_workspace_delete_removes_website_data(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)

    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    deleted = await client.delete(
        f"/workspaces/{workspace_id}", headers=headers
    )
    assert deleted.status_code == 204, deleted.text

    async with get_db() as db:
        for table in ("website_sources", "website_pages", "website_sync_jobs"):
            async with db.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE workspace_id = ?",
                (workspace_id,),
            ) as cur:
                assert (await cur.fetchone())["n"] == 0
        async with db.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 0


@pytest.mark.asyncio
async def test_free_website_source_limit_is_enforced(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _free_workspace(client, headers)

    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/", "refresh_policy": "manual"},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    blocked = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/second", "refresh_policy": "manual"},
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    detail = blocked.json()["detail"]
    assert detail["resource"] == "website_sources"
    assert detail["used"] == 1 and detail["limit"] == 1
    assert detail["plan"] == "free"


@pytest.mark.asyncio
async def test_free_plan_refuses_daily_website_refresh(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _free_workspace(client, headers)

    blocked = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/", "refresh_policy": "daily"},
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    detail = blocked.json()["detail"]
    assert detail["resource"] == "website_refresh"
    assert detail["used"] == "daily" and detail["limit"] == "manual"
    assert detail["plan"] == "free"


@pytest.mark.asyncio
async def test_expired_trial_downgrades_daily_source_on_refresh(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)

    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/", "refresh_policy": "daily"},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    # Trial expires while the source still has its daily cadence.
    async with get_db() as db:
        await plan_service.set_workspace_plan(db, workspace_id, "free")
        await db.execute(
            "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = (SELECT owner_id FROM workspaces WHERE id = ?)",
            (workspace_id,),
        )
        await db.commit()

    refreshed = await client.post(
        f"/workspaces/{workspace_id}/websites/{source_id}/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 202, refreshed.text

    async with get_db() as db:
        async with db.execute(
            "SELECT refresh_policy, next_sync_at FROM website_sources WHERE id = ?",
            (source_id,),
        ) as cur:
            source = await cur.fetchone()
    assert source["refresh_policy"] == "manual"
    assert source["next_sync_at"] is None


@pytest.mark.asyncio
async def test_free_indexed_page_limit_blocks_new_pages_only(client, monkeypatch):
    _install_fakes(monkeypatch)
    headers = await _register(client)
    workspace_id = await _free_workspace(client, headers)

    created = await client.post(
        f"/workspaces/{workspace_id}/websites",
        json={"url": "https://example.com/", "refresh_policy": "manual"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await _wait_for_sync(client, headers, workspace_id, source_id)

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM website_pages WHERE workspace_id = ?",
            (workspace_id,),
        ) as cur:
            existing = (await cur.fetchone())["n"]
        for index in range(existing, 50):
            await db.execute(
                """INSERT INTO website_pages
                   (id, source_id, workspace_id, url, title, content_hash,
                    status, chunk_count, error_message, last_indexed_at,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'indexed', 1, NULL, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    source_id,
                    workspace_id,
                    f"https://example.com/page-{index}",
                    f"Page {index}",
                    f"hash-{index}",
                    "2026-10-01T00:00:00+00:00",
                    "2026-10-01T00:00:00+00:00",
                ),
            )
        await db.commit()

        with pytest.raises(HTTPException) as exc:
            await plan_service.assert_can_index_page(db, workspace_id)
        assert exc.value.status_code == 403
        assert exc.value.detail["resource"] == "pages_indexed"
        assert exc.value.detail["used"] == 50
        assert exc.value.detail["limit"] == 50

        # Re-indexing an existing page replaces its slot, so the limit allows it.
        await plan_service.assert_can_index_page(db, workspace_id, replacing=True)
