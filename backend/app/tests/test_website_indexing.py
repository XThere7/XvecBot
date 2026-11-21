"""Website indexing regression tests.

These cover the static/metadata extraction fallback, optional JavaScript
rendering, truthful partial/failure statuses and the SSRF boundary. No test
depends on HuaweiDIT.com being online.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from ..core import ssrf_guard
from ..core.database import get_db
from ..services import website_crawler, website_training_service


def _full_page() -> str:
    return """
    <html><head><title>Pricing</title></head><body>
      <nav>Home Pricing Contact</nav>
      <main>
        <h1>Simple pricing</h1>
        <p>Our starter plan begins at fifty thousand shillings per month and
        includes onboarding, support and a knowledge base with up to fifty
        documents. The growth plan adds more agents and priority support.</p>
        <p>All plans are billed monthly and can be cancelled at any time.</p>
      </main>
      <footer>Copyright example</footer>
    </body></html>
    """


def _spa_shell() -> str:
    return """
    <html><head>
      <title>Huawei DIT ICT Academy | ICT Training and Certifications</title>
      <meta name="description" content="Join the Huawei DIT ICT Academy at the
      Dar es Salaam Institute of Technology. Huawei-certified training in
      networking, cloud, AI, cybersecurity, WLAN and big data for future ICT
      leaders in Tanzania." />
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"EducationalOrganization",
       "name":"Huawei DIT ICT Academy",
       "description":"Empowering future ICT leaders through high-class training
       and Huawei certifications at the Dar es Salaam Institute of Technology."}
      </script>
      <script type="module" src="/assets/app.js"></script>
    </head><body><div id="root"></div></body></html>
    """


def test_extract_full_html_prefers_body_text():
    title, text, quality = website_crawler.extract_text_details(
        _full_page(), "https://example.com/pricing"
    )
    assert title == "Pricing"
    assert quality == "full"
    assert "fifty thousand shillings" in text
    assert "Copyright example" not in text


def test_extract_spa_shell_uses_metadata_fallback():
    title, text, quality = website_crawler.extract_text_details(
        _spa_shell(), "https://huaweidit.com/"
    )
    assert "Huawei DIT" in title
    assert quality == "metadata"
    assert "networking, cloud, AI" in text
    assert "Dar es Salaam Institute of Technology" in text


def test_script_only_page_has_no_extractable_text():
    html = "<html><head><title>App</title></head><body><div id='root'></div><script>var x = 1;</script></body></html>"
    _title, _text, quality = website_crawler.extract_text_details(
        html, "https://example.com/"
    )
    assert quality == "empty"
    with pytest.raises(website_crawler.CrawlError):
        website_crawler.extract_text(html, "https://example.com/")


class _FakeRenderer:
    def __init__(self, html: str):
        self.html = html
        self.calls = 0

    async def render(self, _url: str):
        self.calls += 1
        return "https://example.com/", self.html


@pytest.mark.asyncio
async def test_fetch_page_uses_renderer_when_static_shell_has_no_body(monkeypatch):
    async def fake_get(url, **_kwargs):
        return url, "text/html; charset=utf-8", _spa_shell().encode()

    monkeypatch.setattr(website_crawler, "_get_bytes", fake_get)
    renderer = _FakeRenderer(
        "<html><head><title>Rendered</title></head><body><main>"
        + "Rendered course content with networking, cloud and cybersecurity "
        + "training for students in Dar es Salaam. " * 5
        + "</main></body></html>"
    )
    final_url, title, text, quality = await website_crawler.fetch_page(
        "https://example.com/", session=object(), renderer=renderer
    )
    assert final_url == "https://example.com/"
    assert title == "Rendered"
    assert quality == "full"
    assert "Rendered course content" in text
    assert renderer.calls == 1


@pytest.mark.asyncio
async def test_fetch_page_falls_back_to_metadata_without_renderer(monkeypatch):
    async def fake_get(url, **_kwargs):
        return url, "text/html; charset=utf-8", _spa_shell().encode()

    monkeypatch.setattr(website_crawler, "_get_bytes", fake_get)
    _url, _title, text, quality = await website_crawler.fetch_page(
        "https://example.com/", session=object()
    )
    assert quality == "metadata"
    assert "Huawei" in text


def test_sync_outcome_is_truthful():
    synced = website_training_service.sync_outcome(
        {"pages_indexed": 2, "pages_unchanged": 0, "pages_failed": 0}, 0
    )
    assert synced["status"] == "synced"
    assert synced["error_message"] is None

    partial = website_training_service.sync_outcome(
        {"pages_indexed": 2, "pages_unchanged": 0, "pages_failed": 1}, 0
    )
    assert partial["status"] == "partial"
    assert "1 page(s) could not be processed" in partial["error_message"]

    metadata_only = website_training_service.sync_outcome(
        {"pages_indexed": 1, "pages_unchanged": 3, "pages_failed": 0}, 4
    )
    assert metadata_only["status"] == "partial"
    assert "JavaScript" in metadata_only["error_message"]

    failed = website_training_service.sync_outcome(
        {"pages_indexed": 0, "pages_unchanged": 0, "pages_failed": 2}, 0
    )
    assert failed["status"] == "failed"
    assert failed["job_status"] == "failed"

    nothing = website_training_service.sync_outcome(
        {"pages_indexed": 0, "pages_unchanged": 0, "pages_failed": 0}, 0
    )
    assert nothing["status"] == "failed"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_ssrf_guard_blocks_private_and_unsupported_urls(url):
    with pytest.raises(HTTPException):
        ssrf_guard.validate_url(url, resolve_dns=False)


@pytest.mark.asyncio
async def test_redirect_to_metadata_endpoint_is_blocked():
    with pytest.raises(HTTPException):
        await ssrf_guard.safe_follow_redirect("http://169.254.169.254/latest/meta-data/")


async def _seed_source(db) -> tuple[str, str, str]:
    user_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, email, hashed_password, is_active, created_at, plan) "
        "VALUES (?, ?, 'x', 1, ?, 'pro')",
        (user_id, f"web-{user_id[:8]}@example.com", now),
    )
    await db.execute(
        "INSERT INTO workspaces (id, name, system_prompt, owner_id, created_at, plan) "
        "VALUES (?, 'Web test', 'Help', ?, ?, 'pro')",
        (workspace_id, user_id, now),
    )
    await db.execute(
        """INSERT INTO website_sources
           (id, workspace_id, url, name, status, pages_discovered, pages_indexed,
            last_synced_at, next_sync_at, refresh_policy, error_message,
            created_at, updated_at)
           VALUES (?, ?, 'https://example.com/', 'example', 'pending', 0, 0,
                   NULL, NULL, 'manual', NULL, ?, ?)""",
        (source_id, workspace_id, now, now),
    )
    await db.commit()
    return user_id, workspace_id, source_id


@pytest.mark.asyncio
async def test_sync_marks_duplicate_content_without_extra_chunks(monkeypatch):
    page_text = (
        "Example Academy offers networking, cloud and cybersecurity training "
        "for students in Dar es Salaam. " * 4
    )

    async def fake_discover(*_args, **_kwargs):
        return ["https://example.com/", "https://example.com/copy"]

    async def fake_fetch(url, **_kwargs):
        return url, "Example", page_text, "full"

    async def fake_index(db, page_id, page_url, title, text, workspace_id, source_id):
        await db.execute(
            "UPDATE website_pages SET status = 'indexed', chunk_count = 1 "
            "WHERE id = ? AND workspace_id = ?",
            (page_id, workspace_id),
        )
        await db.commit()
        return 1

    monkeypatch.setattr(website_crawler, "discover_pages", fake_discover)
    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch)
    monkeypatch.setattr(website_training_service, "index_page", fake_index)

    async with get_db() as db:
        _user_id, workspace_id, source_id = await _seed_source(db)
        result = await website_training_service.sync_website_source(
            source_id, db=db, already_claimed=True
        )
        assert result["pages_indexed"] == 1
        assert result["pages_unchanged"] == 1

        source = await (
            await db.execute(
                "SELECT * FROM website_sources WHERE id = ?", (source_id,)
            )
        ).fetchone()
        assert source["status"] == "synced"
        assert source["pages_indexed"] == 1

        pages = await (
            await db.execute(
                "SELECT status, url FROM website_pages WHERE source_id = ? "
                "ORDER BY url",
                (source_id,),
            )
        ).fetchall()
        statuses = {row["status"] for row in pages}
        assert "indexed" in statuses
        assert "duplicate" in statuses
        assert sum(1 for row in pages if row["status"] == "indexed") == 1


@pytest.mark.asyncio
async def test_sync_partial_when_one_page_fails(monkeypatch):
    page_text = "Useful website content about services and pricing. " * 5

    async def fake_discover(*_args, **_kwargs):
        return ["https://example.com/", "https://example.com/broken"]

    async def fake_fetch(url, **_kwargs):
        if url.endswith("/broken"):
            raise website_crawler.CrawlError("Page returned HTTP 500.")
        return url, "Example", page_text, "full"

    async def fake_index(db, page_id, page_url, title, text, workspace_id, source_id):
        await db.execute(
            "UPDATE website_pages SET status = 'indexed', chunk_count = 1 "
            "WHERE id = ? AND workspace_id = ?",
            (page_id, workspace_id),
        )
        await db.commit()
        return 1

    monkeypatch.setattr(website_crawler, "discover_pages", fake_discover)
    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch)
    monkeypatch.setattr(website_training_service, "index_page", fake_index)

    async with get_db() as db:
        _user_id, _workspace_id, source_id = await _seed_source(db)
        result = await website_training_service.sync_website_source(
            source_id, db=db, already_claimed=True
        )
        assert result["pages_indexed"] == 1
        assert result["pages_failed"] == 1

        source = await (
            await db.execute(
                "SELECT * FROM website_sources WHERE id = ?", (source_id,)
            )
        ).fetchone()
        assert source["status"] == "partial"
        assert "1 page(s) could not be processed" in source["error_message"]
