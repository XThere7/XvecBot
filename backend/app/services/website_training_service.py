"""
services/website_training_service.py

Indexes crawled website pages through the *existing* RAG pipeline:
chunker -> embedder -> indexer.

Each page is a virtual document. A page gets a shadow ``documents`` row plus a
``workspace_documents`` row so the retrieval layer's existing
``status = 'ready'`` join works without being changed. The page id is used as
the document id, which is also how citations recover the source URL.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core.database import get_db
from ..core.logging import get_logger
from ..core.plan import refresh_policy_rank
from ..ingestion.chunker import chunk_document
from ..ingestion.embedder import embed_texts
from ..ingestion.indexer import index_chunks
from ..ingestion.pdf_loader import PageContent
from ..storage import vector_store
from . import plan_service, website_crawler

log = get_logger(__name__)

MAX_ERROR_LENGTH = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: object) -> str:
    text = str(value or "")
    return text[:MAX_ERROR_LENGTH]


def _content_hash(text: str) -> str:
    """Hash the same whitespace-trimmed text that index_page indexes."""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _next_sync_at(policy: str, now: datetime) -> Optional[str]:
    if policy == "daily":
        return (now + timedelta(days=1)).isoformat()
    if policy == "weekly":
        return (now + timedelta(days=7)).isoformat()
    return None


async def _page_exists(
    db,
    page_id: str,
    workspace_id: str,
    source_id: str,
) -> bool:
    async with db.execute(
        """SELECT 1
           FROM website_pages wp
           JOIN website_sources ws ON ws.id = wp.source_id
           WHERE wp.id = ? AND wp.workspace_id = ?
             AND wp.source_id = ? AND ws.workspace_id = ?""",
        (page_id, workspace_id, source_id, workspace_id),
    ) as cur:
        return await cur.fetchone() is not None


async def _prepare_document_rows(
    db,
    *,
    page_id: str,
    workspace_id: str,
    title: str,
    url: str,
) -> None:
    """Create/refresh the shadow rows retrieval and FKs expect."""
    now = _now()
    filename = (title or url).strip() or url

    async with db.execute(
        "SELECT id FROM workspace_documents WHERE id = ?", (page_id,)
    ) as cur:
        exists = await cur.fetchone() is not None
    if exists:
        await db.execute(
            """UPDATE workspace_documents
               SET filename = ?, status = 'processing', chunk_count = 0,
                   file_path = '', file_type = 'website', size_bytes = 0
               WHERE id = ? AND workspace_id = ?""",
            (filename, page_id, workspace_id),
        )
    else:
        await db.execute(
            """INSERT INTO workspace_documents
               (id, workspace_id, filename, file_path, file_type, size_bytes,
                status, chunk_count, created_at)
               VALUES (?, ?, ?, '', 'website', 0, 'processing', 0, ?)""",
            (page_id, workspace_id, filename, now),
        )

    async with db.execute(
        "SELECT id FROM documents WHERE id = ?", (page_id,)
    ) as cur:
        exists = await cur.fetchone() is not None
    if exists:
        await db.execute(
            """UPDATE documents
               SET filename = ?, upload_date = ?, total_pages = 1,
                   file_size = 0, status = 'ready'
               WHERE id = ?""",
            (filename, now, page_id),
        )
    else:
        await db.execute(
            """INSERT INTO documents
               (id, filename, upload_date, total_pages, file_size, status)
               VALUES (?, ?, ?, 1, 0, 'ready')""",
            (page_id, filename, now),
        )
    await db.commit()


async def _mark_workspace_document_ready(
    db, page_id: str, workspace_id: str, title: str, chunk_count: int
) -> None:
    await db.execute(
        """UPDATE workspace_documents
           SET filename = ?, status = 'ready', chunk_count = ?
           WHERE id = ? AND workspace_id = ?""",
        ((title or page_id), chunk_count, page_id, workspace_id),
    )
    await db.execute(
        "UPDATE documents SET filename = ?, status = 'ready' WHERE id = ?",
        ((title or page_id), page_id),
    )
    await db.commit()


async def index_page(
    db,
    page_id: str,
    page_url: str,
    page_title: str,
    page_text: str,
    workspace_id: str,
    source_id: str,
) -> int:
    """
    Run one page through the existing chunker, embedder and indexer.

    The page row must already exist. Returns the number of chunks stored.
    Raises on failure; the sync job records the page as failed and cleans up.
    """
    text = (page_text or "").strip()
    if not text:
        raise ValueError("Page has no extractable text.")

    title = (page_title or page_url).strip() or page_url

    pages = [PageContent(page_number=1, text=text, char_count=len(text))]
    chunks = await asyncio.to_thread(chunk_document, pages)
    if not chunks:
        raise ValueError("Page produced no chunks.")

    embeddings = await asyncio.to_thread(embed_texts, [chunk.text for chunk in chunks])

    # The owner may delete the source while extraction/embedding is running.
    if not await _page_exists(db, page_id, workspace_id, source_id):
        log.info("Website page indexing abandoned: page deleted", page_id=page_id)
        return 0

    await _prepare_document_rows(
        db,
        page_id=page_id,
        workspace_id=workspace_id,
        title=title,
        url=page_url,
    )

    # Idempotent re-index: remove any previous chunks/embeddings for this page.
    await vector_store.delete_embeddings_for_document(db, page_id)
    await db.execute(
        "DELETE FROM chunks WHERE workspace_id = ? AND (document_id = ? OR doc_id = ?)",
        (workspace_id, page_id, page_id),
    )
    await db.commit()

    chunk_ids = await index_chunks(
        db,
        page_id,
        chunks,
        embeddings,
        metadata={
            "workspace_id": workspace_id,
            "doc_id": page_id,
            "filename": title,
            "source_type": "website",
            "source_url": page_url,
        },
    )

    # A deletion can race the index write. Clean up the rows we just inserted.
    if not await _page_exists(db, page_id, workspace_id, source_id):
        await remove_page_chunks(db, page_id, workspace_id)
        log.info("Website page indexing abandoned after deletion", page_id=page_id)
        return 0

    content_hash = _content_hash(text)
    now = _now()
    await db.execute(
        """UPDATE website_pages
           SET title = ?, content_hash = ?, status = 'indexed',
               chunk_count = ?, error_message = NULL, last_indexed_at = ?
           WHERE id = ? AND workspace_id = ?""",
        (title, content_hash, len(chunk_ids), now, page_id, workspace_id),
    )
    await _mark_workspace_document_ready(
        db, page_id, workspace_id, title, len(chunk_ids)
    )
    log.info(
        "Website page indexed",
        page_id=page_id,
        source_id=source_id,
        workspace_id=workspace_id,
        chunks=len(chunk_ids),
    )
    return len(chunk_ids)


async def remove_page_chunks(db, page_id: str, workspace_id: str) -> None:
    """Remove a virtual document's vectors, chunks, and shadow rows."""
    await vector_store.delete_embeddings_for_document(db, page_id)
    await db.execute(
        "DELETE FROM chunks WHERE workspace_id = ? AND (document_id = ? OR doc_id = ?)",
        (workspace_id, page_id, page_id),
    )
    await db.execute(
        "DELETE FROM workspace_documents WHERE id = ? AND workspace_id = ? "
        "AND file_type = 'website'",
        (page_id, workspace_id),
    )
    await db.execute(
        """DELETE FROM documents
           WHERE id = ?
             AND NOT EXISTS (SELECT 1 FROM workspace_documents WHERE id = ?)""",
        (page_id, page_id),
    )
    await db.commit()


async def _set_page_failure(db, page_id: str, error: object) -> None:
    await db.execute(
        """UPDATE website_pages
           SET status = 'failed', chunk_count = 0, content_hash = NULL,
               error_message = ?
           WHERE id = ?""",
        (_truncate(error), page_id),
    )
    await db.commit()


async def _create_job(
    db, *, source_id: str, workspace_id: str, triggered_by: str
) -> str:
    job_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO website_sync_jobs
           (id, source_id, workspace_id, triggered_by, status, pages_crawled,
            pages_indexed, pages_unchanged, pages_failed, started_at)
           VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0, ?)""",
        (job_id, source_id, workspace_id, triggered_by, _now()),
    )
    await db.commit()
    return job_id


async def _finish_job(
    db,
    *,
    job_id: str,
    status: str,
    counts: dict,
    error: Optional[str] = None,
) -> None:
    await db.execute(
        """UPDATE website_sync_jobs
           SET status = ?, pages_crawled = ?, pages_indexed = ?,
               pages_unchanged = ?, pages_failed = ?, error_message = ?,
               finished_at = ?
           WHERE id = ?""",
        (
            status,
            counts.get("pages_crawled", 0),
            counts.get("pages_indexed", 0),
            counts.get("pages_unchanged", 0),
            counts.get("pages_failed", 0),
            _truncate(error) if error else None,
            _now(),
            job_id,
        ),
    )
    await db.commit()


async def _fail_source(
    db,
    *,
    source_id: str,
    job_id: str,
    counts: dict,
    error: object,
    next_sync_at: Optional[str] = None,
) -> None:
    message = _truncate(error)
    await db.execute(
        """UPDATE website_sources
           SET status = 'failed', error_message = ?, next_sync_at = ?,
               updated_at = ?
           WHERE id = ?""",
        (message, next_sync_at, _now(), source_id),
    )
    await db.commit()
    await _finish_job(db, job_id=job_id, status="failed", counts=counts, error=message)


async def recover_stale_syncs() -> int:
    """
    Mark syncs left ``running``/``syncing`` by a previous process as failed.

    Crawls run as in-process background tasks. If the process exits mid-sync,
    the rows would otherwise stay claimed forever: the source could not be
    refreshed or deleted, and scheduled refreshes would skip it. Startup calls
    this before the scheduler starts. Single-worker deployment assumption
    matches the in-process rate limiter and scheduler.
    """
    now = datetime.now(timezone.utc)
    message = "The previous sync was interrupted by a server restart."
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM website_sources WHERE status = 'syncing'"
        ) as cur:
            row = await cur.fetchone()
        stale_sources = int(row["n"] if row is not None else 0)

        await db.execute(
            """UPDATE website_sync_jobs
               SET status = 'failed', error_message = ?, finished_at = ?
               WHERE status = 'running'""",
            (message, now.isoformat()),
        )
        await db.execute(
            """UPDATE website_sources
               SET status = 'failed', error_message = ?, updated_at = ?
               WHERE status = 'syncing'""",
            (message, now.isoformat()),
        )
        await db.commit()

    if stale_sources:
        log.warning("Recovered stale website syncs", count=stale_sources)
    return stale_sources


async def _existing_index_rows(db, page_id: str, workspace_id: str) -> bool:
    async with db.execute(
        """SELECT 1 FROM workspace_documents
           WHERE id = ? AND workspace_id = ? AND status = 'ready'
             AND file_type = 'website'""",
        (page_id, workspace_id),
    ) as cur:
        if await cur.fetchone() is None:
            return False
    async with db.execute(
        "SELECT 1 FROM chunks WHERE workspace_id = ? AND doc_id = ? LIMIT 1",
        (workspace_id, page_id),
    ) as cur:
        return await cur.fetchone() is not None


async def sync_website_source(
    source_id: str,
    *,
    triggered_by: str = "manual",
    db=None,
    already_claimed: bool = False,
):
    """
    Crawl and index one website source.

    This never lets an exception escape to a background-task runner: every
    failure is recorded on the source and the sync job. Safe to call without a
    connection (background tasks) or with an active one.
    """
    if db is None:
        async with get_db() as connection:
            return await sync_website_source(
                source_id,
                triggered_by=triggered_by,
                db=connection,
                already_claimed=already_claimed,
            )

    async with db.execute(
        "SELECT * FROM website_sources WHERE id = ?", (source_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        log.warning("Website sync skipped: source not found", source_id=source_id)
        return {
            "pages_crawled": 0,
            "pages_indexed": 0,
            "pages_unchanged": 0,
            "pages_failed": 0,
            "skipped": True,
        }

    source = dict(row)
    workspace_id = source["workspace_id"]
    allowed_policy = await plan_service.allowed_refresh_policy_for_workspace(
        db, workspace_id
    )
    source_policy = source.get("refresh_policy") or "manual"
    if refresh_policy_rank(source_policy) > refresh_policy_rank(allowed_policy):
        # The account may have left its trial (or a paid plan lapsed) while a
        # source still had a daily/weekly cadence. Clamp it before doing any
        # crawl work so a scheduled tick cannot bypass the current plan.
        now = datetime.now(timezone.utc)
        await db.execute(
            "UPDATE website_sources SET refresh_policy = ?, next_sync_at = ?, "
            "updated_at = ? WHERE id = ?",
            (
                allowed_policy,
                _next_sync_at(allowed_policy, now),
                _now(),
                source_id,
            ),
        )
        await db.commit()
        source["refresh_policy"] = allowed_policy
        if triggered_by == "scheduled":
            log.info(
                "Scheduled website sync skipped: refresh policy downgraded",
                source_id=source_id,
                allowed_policy=allowed_policy,
            )
            return {
                "pages_crawled": 0,
                "pages_indexed": 0,
                "pages_unchanged": 0,
                "pages_failed": 0,
                "skipped": True,
            }
    if not already_claimed:
        # Compare-and-set claim. Two refresh requests (or a scheduler tick
        # racing a manual refresh) must never crawl the same source twice.
        claimed = await db.execute(
            """UPDATE website_sources
               SET status = 'syncing', updated_at = ?
               WHERE id = ? AND status != 'syncing'
               RETURNING id""",
            (_now(), source_id),
        )
        if await claimed.fetchone() is None:
            log.info("Website sync skipped: already running", source_id=source_id)
            return {
                "pages_crawled": 0,
                "pages_indexed": 0,
                "pages_unchanged": 0,
                "pages_failed": 0,
                "skipped": True,
            }
        await db.commit()

    counts = {
        "pages_crawled": 0,
        "pages_indexed": 0,
        "pages_unchanged": 0,
        "pages_failed": 0,
    }
    job_id: Optional[str] = None
    try:
        job_id = await _create_job(
            db,
            source_id=source_id,
            workspace_id=workspace_id,
            triggered_by=triggered_by,
        )
        client = website_crawler.build_client()
    except Exception as exc:
        log.error("Could not start website sync", source_id=source_id, error=str(exc))
        try:
            await db.execute(
                "UPDATE website_sources SET status = 'failed', error_message = ?, "
                "next_sync_at = ?, updated_at = ? WHERE id = ?",
                (
                    _truncate(exc),
                    _next_sync_at(
                        source.get("refresh_policy") or "manual",
                        datetime.now(timezone.utc),
                    ),
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
            if job_id:
                await _finish_job(
                    db, job_id=job_id, status="failed", counts=counts, error=str(exc)
                )
        except Exception as cleanup_exc:
            log.error(
                "Could not record website sync startup failure",
                source_id=source_id,
                error=str(cleanup_exc),
            )
        return counts

    async with client as session:
        try:
            discovered = await website_crawler.discover_pages(
                source["url"],
                max_pages=website_crawler.MAX_PAGES_PER_SOURCE,
                session=session,
            )
            discovered = list(
                dict.fromkeys(
                    website_crawler.normalise_url(u) for u in discovered
                )
            )[: website_crawler.MAX_PAGES_PER_SOURCE]
            if not discovered:
                raise website_crawler.CrawlError(
                    "No crawlable pages were found for this website."
                )

            async with db.execute(
                "SELECT * FROM website_pages WHERE source_id = ?", (source_id,)
            ) as cur:
                existing_pages = [dict(r) for r in await cur.fetchall()]
            by_url = {
                website_crawler.normalise_url(page["url"]): page
                for page in existing_pages
            }

            for index, page_url in enumerate(discovered):
                page = by_url.get(page_url)
                page_id = page["id"] if page is not None else str(uuid.uuid4())

                if page is None:
                    await db.execute(
                        """INSERT INTO website_pages
                           (id, source_id, workspace_id, url, title, content_hash,
                            status, chunk_count, error_message, last_indexed_at,
                            created_at)
                           VALUES (?, ?, ?, ?, NULL, NULL, 'discovered', 0, NULL,
                                   NULL, ?)""",
                        (page_id, source_id, workspace_id, page_url, _now()),
                    )
                    await db.commit()

                try:
                    final_url, title, text = await website_crawler.fetch_page(
                        page_url, session=session
                    )
                    counts["pages_crawled"] += 1
                    content_hash = _content_hash(text)

                    unchanged = (
                        page is not None
                        and page.get("status") == "indexed"
                        and page.get("content_hash") == content_hash
                        and await _existing_index_rows(db, page_id, workspace_id)
                    )
                    if unchanged:
                        await db.execute(
                            """UPDATE website_pages
                               SET title = ?, error_message = NULL
                               WHERE id = ?""",
                            (title or page_url, page_id),
                        )
                        await _mark_workspace_document_ready(
                            db,
                            page_id,
                            workspace_id,
                            title or page_url,
                            int(page.get("chunk_count") or 0),
                        )
                        counts["pages_unchanged"] += 1
                        continue

                    # New pages consume the workspace's indexed-page allowance.
                    # Re-indexing a page that was already indexed replaces it
                    # one-for-one and therefore does not consume a new slot.
                    was_indexed = (
                        page is not None and page.get("status") == "indexed"
                    )
                    await plan_service.assert_can_index_page(
                        db, workspace_id, replacing=was_indexed
                    )

                    # Changed or new: drop the old virtual document first so
                    # stale chunks cannot answer with outdated content.
                    await remove_page_chunks(db, page_id, workspace_id)
                    await db.execute(
                        """UPDATE website_pages
                           SET title = ?, status = 'discovered', chunk_count = 0,
                               error_message = NULL, content_hash = NULL
                           WHERE id = ?""",
                        (title or final_url or page_url, page_id),
                    )
                    await db.commit()

                    chunk_count = await index_page(
                        db,
                        page_id,
                        final_url or page_url,
                        title,
                        text,
                        workspace_id,
                        source_id,
                    )
                    if chunk_count > 0:
                        counts["pages_indexed"] += 1
                except Exception as exc:
                    counts["pages_failed"] += 1
                    log.warning(
                        "Website page sync failed",
                        source_id=source_id,
                        url=page_url,
                        error=str(exc),
                    )
                    try:
                        await remove_page_chunks(db, page_id, workspace_id)
                        await _set_page_failure(db, page_id, exc)
                    except Exception as cleanup_exc:
                        log.error(
                            "Website page cleanup failed",
                            page_id=page_id,
                            error=str(cleanup_exc),
                        )

                if index < len(discovered) - 1:
                    await asyncio.sleep(website_crawler.REQUEST_DELAY_SECONDS)

            # Pages that disappeared from discovery are no longer part of the
            # knowledge source. Their chunks must go too.
            discovered_set = set(discovered)
            for page in existing_pages:
                page_url = website_crawler.normalise_url(page["url"])
                if page_url in discovered_set:
                    continue
                try:
                    await remove_page_chunks(db, page["id"], workspace_id)
                    await db.execute(
                        """UPDATE website_pages
                           SET status = 'removed', chunk_count = 0,
                               content_hash = NULL, error_message = NULL
                           WHERE id = ?""",
                        (page["id"],),
                    )
                    await db.commit()
                except Exception as exc:
                    log.warning(
                        "Could not remove stale website page",
                        page_id=page["id"],
                        error=str(exc),
                    )

            now = datetime.now(timezone.utc)
            async with db.execute(
                """SELECT COUNT(*) AS n FROM website_pages
                   WHERE source_id = ? AND status = 'indexed'""",
                (source_id,),
            ) as cur:
                indexed_row = await cur.fetchone()
            indexed_count = int(indexed_row["n"] if indexed_row is not None else 0)

            failed = counts["pages_failed"]
            succeeded = counts["pages_indexed"] + counts["pages_unchanged"]
            source_status = "failed" if failed and not succeeded else "synced"
            error_message = (
                f"{failed} page(s) could not be indexed."
                if source_status == "failed"
                else None
            )

            await db.execute(
                """UPDATE website_sources
                   SET status = ?, pages_discovered = ?, pages_indexed = ?,
                       last_synced_at = ?, next_sync_at = ?,
                       error_message = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    source_status,
                    len(discovered),
                    indexed_count,
                    # A failed sync is not a successful refresh; keep the old
                    # timestamp so the manual-refresh cooldown does not punish
                    # the user for a failure that made no progress.
                    (
                        now.isoformat()
                        if source_status == "synced"
                        else source.get("last_synced_at")
                    ),
                    _next_sync_at(source.get("refresh_policy") or "manual", now),
                    error_message,
                    now.isoformat(),
                    source_id,
                ),
            )
            await db.commit()
            await _finish_job(
                db,
                job_id=job_id,
                status="completed" if source_status == "synced" else "failed",
                counts=counts,
                error=error_message,
            )
            log.info(
                "Website sync complete",
                source_id=source_id,
                status=source_status,
                **counts,
            )
            return counts
        except Exception as exc:
            log.error("Website sync failed", source_id=source_id, error=str(exc))
            try:
                await _fail_source(
                    db,
                    source_id=source_id,
                    job_id=job_id,
                    counts=counts,
                    error=exc,
                    next_sync_at=_next_sync_at(
                        source.get("refresh_policy") or "manual",
                        datetime.now(timezone.utc),
                    ),
                )
            except Exception as cleanup_exc:
                log.error(
                    "Could not record website sync failure",
                    source_id=source_id,
                    error=str(cleanup_exc),
                )
            return counts
