"""Focused tests for agent-scoped public social media imports.

Public extraction is faked (no internet). The rest is real: SQLite schema,
de-duplication, manual fallback, background indexing, chunk scoping, citations,
deletion, plan limits, and agent/workspace isolation.
"""
import asyncio
import uuid

import pytest

from app.core.config import settings
from app.core.database import get_db
from app.retrieval.hybrid_search import hybrid_search
from app.services import plan_service, social_media_service
from app.services.social_media_service import (
    ExtractedPost,
    MediaFetchError,
    MediaValidationError,
    parse_media_url,
)
from app.services.workspace_query_service import (
    _build_sources,
    _source_metadata_for_chunks,
)
from app.storage import sqlite as db_ops

POST_TEXT = (
    "Our new morning blend is now available at the downtown shop. "
    "It is roasted in small batches and has notes of cocoa, orange and "
    "brown sugar. Open from 7am every weekday."
)

TIKTOK_OK = "https://www.tiktok.com/@acme.coffee/video/7300000000000000000"
INSTAGRAM_OK = "https://www.instagram.com/p/CxYzAbCdEfG/"
FACEBOOK_OK = "https://www.facebook.com/acmecoffee/posts/1234567890"


async def _register(client) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"media-{uuid.uuid4().hex[:12]}@example.com",
            "password": "pw123456",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _workspace(client, headers: dict, plan: str | None = None) -> str:
    response = await client.post(
        "/workspaces",
        json={"name": f"Media {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace_id = response.json()["id"]
    if plan:
        async with get_db() as db:
            await plan_service.set_workspace_plan(db, workspace_id, plan)
            # This suite exercises the legacy workspace-level social-media
            # limit. New registrations start on a 21-day Pro trial, which
            # would otherwise mask the Free plan's smaller allowance.
            await db.execute(
                "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = (SELECT owner_id FROM workspaces WHERE id = ?)",
                (workspace_id,),
            )
            await db.commit()
    return workspace_id


async def _agent(client, headers: dict, workspace_id: str, name: str = "Media Agent") -> str:
    response = await client.post(
        f"/workspaces/{workspace_id}/agents",
        json={
            "name": name,
            "system_prompt": "Answer from the business's imported social posts.",
            "model": "meta-llama/llama-3.1-8b-instruct",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _install_fake_extraction(monkeypatch, text: str = POST_TEXT, fail=None):
    calls = {"count": 0}

    async def fake_extract(parsed):
        calls["count"] += 1
        if fail is not None:
            raise fail
        return ExtractedPost(
            title="Acme Coffee: morning blend",
            content_text=text,
            author_name="@acme.coffee",
            published_at="2026-10-20T08:00:00+00:00",
            thumbnail_url=None,
            extraction_method="oembed",
            final_url=parsed.url,
        )

    def fake_embed(texts):
        return [[0.1] * settings.embedding_dimension for _ in texts]

    monkeypatch.setattr(social_media_service, "extract_public_post", fake_extract)
    monkeypatch.setattr(social_media_service, "embed_texts", fake_embed)
    return calls


async def _list(client, headers, workspace_id, agent_id):
    response = await client.get(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _wait_status(
    client, headers, workspace_id, agent_id, source_id, statuses: set[str]
):
    for _ in range(120):
        payload = await _list(client, headers, workspace_id, agent_id)
        for source in payload["sources"]:
            if source["id"] == source_id and source["status"] in statuses:
                return source
        await asyncio.sleep(0.05)
    raise AssertionError(f"media source did not reach {statuses}")


async def _add(client, headers, workspace_id, agent_id, url=TIKTOK_OK):
    response = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media",
        json={"url": url},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _import(
    client, headers, workspace_id, agent_id, source_id
):
    response = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media/sync",
        json={"source_ids": [source_id]},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return await _wait_status(
        client, headers, workspace_id, agent_id, source_id, {"imported", "failed"}
    )


def test_parse_media_urls_and_rejects_profiles_and_foreign_hosts():
    tiktok = parse_media_url(
        "https://m.tiktok.com/@acme.coffee/video/7300000000000000000?is_from_webapp=1"
    )
    assert tiktok.platform == "tiktok"
    assert tiktok.provider_post_id == "7300000000000000000"
    assert tiktok.normalized_url.startswith("https://www.tiktok.com/@acme.coffee/video/")

    instagram = parse_media_url(
        "https://instagram.com/reel/CxYzAbCdEfG/?igsh=tracking"
    )
    assert instagram.normalized_url == "https://www.instagram.com/reel/CxYzAbCdEfG/"

    facebook = parse_media_url(FACEBOOK_OK)
    assert facebook.provider_post_id == "1234567890"

    for url in (
        "https://www.tiktok.com/@acme.coffee",
        "https://www.instagram.com/acme.coffee/",
        "https://example.com/post/1",
        "javascript:alert(1)",
        "http://127.0.0.1/post",
    ):
        with pytest.raises(MediaValidationError):
            parse_media_url(url)


def test_parse_html_metadata_uses_open_graph_and_drops_login_wall():
    html = """
    <html><head>
      <meta property="og:title" content="Acme Coffee on TikTok">
      <meta property="og:description" content="Our new morning blend is now
        available downtown. Roasted in small batches with cocoa and orange.">
      <meta property="article:published_time" content="2026-10-20T08:00:00Z">
      <script type="application/ld+json">
        {"@type":"SocialMediaPosting","author":{"name":"Acme Coffee"}}
      </script>
    </head><body></body></html>
    """
    post = social_media_service._parse_html_metadata(
        html, platform="tiktok", author_hint=None
    )
    assert "morning blend" in post.content_text
    assert post.author_name == "Acme Coffee"
    assert post.published_at == "2026-10-20T08:00:00Z"

    login_wall = "<html><body>Log in or sign up to view this post</body></html>"
    wall = social_media_service._parse_html_metadata(
        login_wall, platform="instagram"
    )
    assert wall.content_text == ""

    # Instagram's public embed stores the caption in JSON rather than meta tags.
    embedded = """
    <html><body><script>
    {"shortcode_media":{"edge_media_to_caption":{"edges":[{"node":{"text":
      "Our roastery is open late this Friday with a free tasting."}}]},
      "taken_at_timestamp":1793054065}}
    </script></body></html>
    """
    post = social_media_service._parse_html_metadata(
        embedded, platform="instagram", embed=True
    )
    assert "roastery is open late" in post.content_text
    assert post.published_at is not None


@pytest.mark.asyncio
async def test_fetch_blocks_private_targets_and_revalidates_redirects(monkeypatch):
    for blocked in (
        "https://127.0.0.1/p/CxYzAbCdEfG/",
        "https://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(MediaFetchError) as exc:
            await social_media_service._allowed_target(
                blocked, ("instagram.com",)
            )
        assert exc.value.code == "blocked_url"

    class RedirectResponse:
        status_code = 302
        headers = {"location": "https://127.0.0.1/internal"}
        url = "https://www.instagram.com/p/CxYzAbCdEfG/"

    class Stream:
        async def __aenter__(self):
            return RedirectResponse()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        streams = 0

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url):
            FakeClient.streams += 1
            return Stream()

    async def allow_public_test_dns(url, *, resolve_dns=True):
        return url

    monkeypatch.setattr(
        social_media_service.ssrf_guard,
        "validate_url_async",
        allow_public_test_dns,
    )
    monkeypatch.setattr(
        social_media_service.httpx, "AsyncClient", FakeClient
    )
    with pytest.raises(MediaFetchError) as exc:
        await social_media_service._fetch_once(
            "https://www.instagram.com/p/CxYzAbCdEfG/",
            allowed_domains=("instagram.com",),
            accept="text/html",
            max_bytes=1000,
        )
    assert exc.value.code == "blocked_url"
    # Redirect destination was revalidated before a second request was made.
    assert FakeClient.streams == 1


@pytest.mark.asyncio
async def test_import_retrieval_citation_isolation_and_delete(client, monkeypatch):
    _install_fake_extraction(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    agent_a = await _agent(client, headers, workspace_id, "Coffee Agent")
    agent_b = await _agent(client, headers, workspace_id, "Other Agent")

    created = await _add(client, headers, workspace_id, agent_a)
    source_id = created["source"]["id"]
    ready = await _wait_status(
        client, headers, workspace_id, agent_a, source_id, {"ready", "awaiting_input"}
    )
    assert ready["status"] == "ready", ready
    assert ready["content_text"] == POST_TEXT
    assert created["usage"] == {"used": 1, "limit": 100}

    imported = await _import(client, headers, workspace_id, agent_a, source_id)
    assert imported["status"] == "imported", imported
    assert imported["chunk_count"] > 0

    async with get_db() as db:
        async with db.execute(
            """SELECT id FROM chunks
               WHERE workspace_id = ? AND agent_id = ? AND doc_id = ?""",
            (workspace_id, agent_a, source_id),
        ) as cur:
            chunk_ids = [row["id"] for row in await cur.fetchall()]
        assert chunk_ids
        chunks = await db_ops.get_chunks_by_ids(db, chunk_ids)
        metadata = await _source_metadata_for_chunks(db, chunks)
        sources = _build_sources(chunks, metadata)
        assert sources[0]["source_url"] == TIKTOK_OK
        assert "morning blend" in sources[0]["filename"].lower()

        # The owning agent can retrieve it in both BM25 and vector paths.
        hits = await hybrid_search(
            db,
            "What coffee blend is available?",
            [0.1] * settings.embedding_dimension,
            workspace_id=workspace_id,
            agent_id=agent_a,
        )
        assert hits

        # Another agent and the workspace-wide chat can never retrieve it.
        other_hits = await hybrid_search(
            db,
            "What coffee blend is available?",
            [0.1] * settings.embedding_dimension,
            workspace_id=workspace_id,
            agent_id=agent_b,
        )
        assert other_hits == []
        workspace_hits = await hybrid_search(
            db,
            "What coffee blend is available?",
            [0.1] * settings.embedding_dimension,
            workspace_id=workspace_id,
        )
        assert workspace_hits == []

    removed = await client.delete(
        f"/workspaces/{workspace_id}/agents/{agent_a}/media/{source_id}",
        headers=headers,
    )
    assert removed.status_code == 204, removed.text
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (source_id,)
        ) as cur:
            assert (await cur.fetchone())["n"] == 0
        async with db.execute(
            "SELECT COUNT(*) AS n FROM social_media_sources WHERE id = ?",
            (source_id,),
        ) as cur:
            assert (await cur.fetchone())["n"] == 0


@pytest.mark.asyncio
async def test_duplicate_url_is_clear_and_does_not_overwrite(client, monkeypatch):
    _install_fake_extraction(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    agent_id = await _agent(client, headers, workspace_id)

    created = await _add(client, headers, workspace_id, agent_id)
    existing_id = created["source"]["id"]
    await _wait_status(
        client, headers, workspace_id, agent_id, existing_id, {"ready", "awaiting_input"}
    )

    duplicate = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media",
        json={"url": TIKTOK_OK.replace("https://www.", "https://m.")},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "duplicate_media"
    assert duplicate.json()["detail"]["existing_source_id"] == existing_id

    # Instagram serves the same media from /p/ and /reel/; the provider post id
    # must de-duplicate those variants even though their paths differ.
    instagram = await _add(
        client, headers, workspace_id, agent_id, url=INSTAGRAM_OK
    )
    instagram_id = instagram["source"]["id"]
    reel_variant = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media",
        json={"url": INSTAGRAM_OK.replace("/p/", "/reel/")},
        headers=headers,
    )
    assert reel_variant.status_code == 409, reel_variant.text
    assert reel_variant.json()["detail"]["existing_source_id"] == instagram_id

    # The second agent may legitimately import the same public post.
    second_agent = await _agent(client, headers, workspace_id, "Second Agent")
    other = await _add(client, headers, workspace_id, second_agent)
    assert other["source"]["id"] != existing_id


@pytest.mark.asyncio
async def test_insufficient_public_text_requires_manual_caption(client, monkeypatch):
    _install_fake_extraction(
        monkeypatch,
        fail=MediaFetchError(
            "insufficient_text",
            "Instagram only exposes this caption to logged-in users. Paste it.",
        ),
    )
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    agent_id = await _agent(client, headers, workspace_id)

    created = await _add(
        client, headers, workspace_id, agent_id, url=INSTAGRAM_OK
    )
    source_id = created["source"]["id"]
    waiting = await _wait_status(
        client, headers, workspace_id, agent_id, source_id, {"awaiting_input", "failed"}
    )
    assert waiting["status"] == "awaiting_input"
    assert "Paste" in waiting["error_message"]

    too_short = await client.patch(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media/{source_id}",
        json={"content_text": "short"},
        headers=headers,
    )
    assert too_short.status_code == 400, too_short.text

    manual = await client.patch(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media/{source_id}",
        json={
            "content_text": (
                "Acme Coffee is launching a new morning blend this Friday. "
                "Visit the downtown shop for a free tasting."
            ),
            "title": "Acme Coffee launch",
        },
        headers=headers,
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["status"] == "ready"
    assert manual.json()["extraction_method"] == "manual"

    imported = await _import(client, headers, workspace_id, agent_id, source_id)
    assert imported["status"] == "imported", imported


@pytest.mark.asyncio
async def test_inaccessible_post_waits_for_input_and_retry(client, monkeypatch):
    calls = _install_fake_extraction(
        monkeypatch,
        fail=MediaFetchError("unavailable", "This post is unavailable."),
    )
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    agent_id = await _agent(client, headers, workspace_id)

    created = await _add(client, headers, workspace_id, agent_id, url=FACEBOOK_OK)
    source_id = created["source"]["id"]
    waiting = await _wait_status(
        client, headers, workspace_id, agent_id, source_id, {"awaiting_input"}
    )
    assert waiting["error_code"] == "unavailable"

    async def success(parsed):
        return ExtractedPost(
            title="Acme Facebook post",
            content_text=POST_TEXT,
            author_name="Acme Coffee",
            published_at=None,
            thumbnail_url=None,
            extraction_method="open_graph",
        )

    monkeypatch.setattr(social_media_service, "extract_public_post", success)
    retried = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media/{source_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 202, retried.text
    ready = await _wait_status(
        client, headers, workspace_id, agent_id, source_id, {"ready", "failed"}
    )
    # The showstopper would be discarding the saved link; the retry path must
    # recover without creating a second source.
    assert ready["status"] == "ready"
    payload = await _list(client, headers, workspace_id, agent_id)
    assert len(payload["sources"]) == 1
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_indexing_failure_is_failed_then_retryable(client, monkeypatch):
    _install_fake_extraction(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers)
    agent_id = await _agent(client, headers, workspace_id)

    created = await _add(client, headers, workspace_id, agent_id)
    source_id = created["source"]["id"]
    await _wait_status(
        client, headers, workspace_id, agent_id, source_id, {"ready"}
    )

    def broken_embed(texts):
        raise RuntimeError("embedding service unavailable")

    monkeypatch.setattr(social_media_service, "embed_texts", broken_embed)
    failed = await _import(client, headers, workspace_id, agent_id, source_id)
    assert failed["status"] == "failed", failed
    assert failed["error_code"] == "indexing_failed"
    assert failed["content_text"] == POST_TEXT
    assert failed["chunk_count"] == 0

    def good_embed(texts):
        return [[0.1] * settings.embedding_dimension for _ in texts]

    monkeypatch.setattr(social_media_service, "embed_texts", good_embed)
    retried = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media/{source_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "ready"
    imported = await _import(client, headers, workspace_id, agent_id, source_id)
    assert imported["status"] == "imported", imported


@pytest.mark.asyncio
async def test_source_limit_and_cross_tenant_isolation(client, monkeypatch):
    _install_fake_extraction(monkeypatch)
    headers = await _register(client)
    workspace_id = await _workspace(client, headers, plan="free")
    agent_id = await _agent(client, headers, workspace_id)

    for index in range(3):
        await _add(
            client,
            headers,
            workspace_id,
            agent_id,
            url=f"https://www.tiktok.com/@acme.coffee/video/73000000000000000{index}",
        )
        await _wait_status(
            client,
            headers,
            workspace_id,
            agent_id,
            (await _list(client, headers, workspace_id, agent_id))["sources"][0]["id"],
            {"ready", "awaiting_input"},
        )

    blocked = await client.post(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media",
        json={"url": "https://www.tiktok.com/@acme.coffee/video/730000000000000009"},
        headers=headers,
    )
    assert blocked.status_code == 402, blocked.text
    detail = blocked.json()["detail"]
    assert detail["resource"] == "social_media_sources"
    assert detail["limit"] == 3

    stranger = await _register(client)
    forbidden = await client.get(
        f"/workspaces/{workspace_id}/agents/{agent_id}/media", headers=stranger
    )
    assert forbidden.status_code == 404
