"""
services/social_media_service.py

Agent-scoped public social media imports.

Only public metadata/oEmbed pages are fetched — there is no login, OAuth or
credential use. Imported text is treated as untrusted knowledge and goes
through the existing chunker -> embedder -> indexer pipeline. Each source owns
a virtual document so citations can recover the original post URL.

The critical isolation rule lives in `chunks.agent_id`: a social media source
belongs to one workspace *and* one agent. Workspace-wide documents keep
`agent_id = NULL` and remain available to every agent.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Optional
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from ..core import ssrf_guard
from ..core.database import get_db
from ..core.logging import get_logger
from ..ingestion.chunker import chunk_document
from ..ingestion.embedder import embed_texts
from ..ingestion.indexer import index_chunks
from ..ingestion.pdf_loader import PageContent
from ..storage import vector_store
from . import plan_service

log = get_logger(__name__)

PLATFORMS = ("tiktok", "instagram", "facebook")
PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
}
PLATFORM_DOMAINS = {
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    # fb.watch is Facebook's short-link domain.
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
}

STATUSES = (
    "pending",
    "extracting",
    "awaiting_input",
    "ready",
    "indexing",
    "imported",
    "failed",
)

MAX_CONTENT_CHARS = 20_000
MAX_MANUAL_CHARS = 20_000
MIN_AUTO_CHARS = 40
MIN_MANUAL_CHARS = 10
MAX_ERROR_LENGTH = 500
MAX_HTML_BYTES = 1_500_000
MAX_JSON_BYTES = 512_000
MAX_REDIRECTS = 5
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_EXTRACTION_ATTEMPTS = 5

USER_AGENT = "BotBaseMediaImport/1.0 (public metadata reader)"

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igsh",
    "igshid",
    "is_from_webapp",
    "sender_device",
    "web_id",
    "_r",
    "_t",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
}

_GENERIC_TEXT_RE = re.compile(
    r"^(?:see instagram photos|log in|sign up|tiktok - make your day|"
    r"facebook|instagram|watch the latest video)",
    re.I,
)

_JSONLD_TYPES = {
    "socialmediaposting",
    "videoobject",
    "article",
    "newsarticle",
    "blogposting",
    "imageobject",
}


class MediaValidationError(Exception):
    """A user-correctable URL/status validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DuplicateMediaError(MediaValidationError):
    """The same post (or identical text) is already in this agent."""

    def __init__(self, existing_source_id: str, message: str):
        super().__init__("duplicate_media", message)
        self.existing_source_id = existing_source_id

    def detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "existing_source_id": self.existing_source_id,
        }


class MediaFetchError(Exception):
    """A public post could not be read, with a user-facing explanation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ParsedMediaUrl:
    platform: str
    url: str
    normalized_url: str
    provider_post_id: Optional[str]


@dataclass
class ExtractedPost:
    title: str
    content_text: str
    author_name: Optional[str]
    published_at: Optional[str]
    thumbnail_url: Optional[str]
    extraction_method: str
    final_url: Optional[str] = None


# ── URL parsing and de-duplication ──────────────────────────────────────────


def _canonical_host(host: str) -> str:
    value = (host or "").rstrip(".").lower()
    for prefix in ("www.", "m.", "web."):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _host_is(host: str, domain: str) -> bool:
    value = _canonical_host(host)
    root = _canonical_host(domain)
    return value == root or value.endswith("." + root)


def platform_for_host(host: str) -> Optional[str]:
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(_host_is(host, domain) for domain in domains):
            return platform
    return None


def _clean_query(query: str) -> str:
    pairs = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    return urlencode(pairs, doseq=True)


def _facebook_query(query: str) -> str:
    keep = {"story_fbid", "id", "fbid", "v", "set"}
    pairs = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() in keep
    ]
    return urlencode(pairs, doseq=True)


def _facebook_post_id(path: str, query: str) -> Optional[str]:
    match = re.search(r"/(?:posts|reel|videos?)/([A-Za-z0-9._-]+)", path)
    if match:
        return match.group(1)
    params = dict(parse_qsl(query, keep_blank_values=True))
    for key in ("story_fbid", "fbid", "v"):
        if params.get(key):
            return params[key]
    return None


def parse_media_url(value: str) -> ParsedMediaUrl:
    """Validate a public post URL and return its de-duplication form.

    Profile/page URLs are rejected: the feature imports a specific post, not
    an entire account. Short-link hosts are accepted and resolved during
    extraction.
    """
    raw = (value or "").strip()
    if not raw:
        raise MediaValidationError("invalid_url", "Enter a social media post URL.")
    if len(raw) > 2048:
        raise MediaValidationError(
            "invalid_url", "Post URLs can be at most 2048 characters."
        )
    if "\\" in raw or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise MediaValidationError("invalid_url", "That URL contains invalid characters.")

    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise MediaValidationError("invalid_url", "That URL is not valid.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise MediaValidationError(
            "invalid_url", "Only public http:// and https:// links are supported."
        )
    if parsed.username or parsed.password:
        raise MediaValidationError(
            "invalid_url", "Post URLs cannot contain usernames or passwords."
        )
    if port is not None and port not in (80, 443):
        raise MediaValidationError(
            "invalid_url", "Non-standard URL ports are not supported."
        )

    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise MediaValidationError("invalid_url", "That URL is not valid.")
    platform = platform_for_host(host)
    if platform is None:
        raise MediaValidationError(
            "unsupported_platform",
            "Only public TikTok, Instagram and Facebook post links are supported.",
        )

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    post_id: Optional[str] = None

    if platform == "tiktok":
        short_host = _canonical_host(host) in {"vm.tiktok.com", "vt.tiktok.com"}
        match = re.search(r"/@([^/]+)/(video|photo)/(\d+)", path)
        if match:
            post_id = match.group(3)
            path = f"/@{match.group(1)}/{match.group(2)}/{post_id}"
        elif not short_host:
            raise MediaValidationError(
                "not_a_post",
                "Enter a link to a specific TikTok video or photo post.",
            )
        canonical_path = path
        canonical_host = "www.tiktok.com"
        normalized_query = _clean_query(parsed.query) if short_host else ""

    elif platform == "instagram":
        match = re.search(r"/(p|reel|tv)/([A-Za-z0-9_-]+)", path)
        if not match:
            raise MediaValidationError(
                "not_a_post",
                "Enter a link to a specific Instagram post or reel.",
            )
        kind, post_id = match.group(1), match.group(2)
        canonical_path = f"/{kind}/{post_id}/"
        canonical_host = "www.instagram.com"
        normalized_query = ""

    else:  # facebook
        short_host = _canonical_host(host) in {"fb.watch", "fb.com"}
        if not short_host:
            looks_like_post = bool(
                re.search(
                    r"/(?:posts|permalink\.php|photo\.php|video\.php|watch|reel|share|videos?)/",
                    path,
                )
                or dict(parse_qsl(parsed.query, keep_blank_values=True)).get(
                    "story_fbid"
                )
            )
            if not looks_like_post:
                raise MediaValidationError(
                    "not_a_post",
                    "Enter a link to a specific Facebook post, photo or video.",
                )
            post_id = _facebook_post_id(path, parsed.query)
        canonical_path = path
        canonical_host = "www.facebook.com" if not short_host else host
        normalized_query = _facebook_query(parsed.query) if not short_host else ""

    normalized = urlunsplit(
        (
            "https",
            canonical_host,
            canonical_path or "/",
            normalized_query,
            "",
        )
    )
    stored_url = urlunsplit(
        (
            "https",
            host,
            path or "/",
            _clean_query(parsed.query),
            "",
        )
    )
    return ParsedMediaUrl(
        platform=platform,
        url=stored_url,
        normalized_url=normalized,
        provider_post_id=post_id,
    )


# ── Safe fetching ───────────────────────────────────────────────────────────


async def _allowed_target(url: str, allowed_domains: tuple[str, ...]) -> None:
    try:
        await ssrf_guard.validate_url_async(url, resolve_dns=True)
    except HTTPException as exc:
        raise MediaFetchError(
            "blocked_url",
            "That URL cannot be fetched safely. Use a public post link from the "
            "supported platforms.",
        ) from exc
    host = urlsplit(url).hostname or ""
    if not any(_host_is(host, domain) for domain in allowed_domains):
        raise MediaFetchError(
            "blocked_url",
            "The link redirected away from its social platform and was not fetched.",
        )


def _decode_body(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > limit:
                raise MediaFetchError("too_large", "That public page is too large to read.")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise MediaFetchError("too_large", "That public page is too large to read.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_once(
    url: str,
    *,
    allowed_domains: tuple[str, ...],
    accept: str,
    max_bytes: int,
) -> tuple[str, str, str]:
    current = url
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=8.0),
            headers=headers,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=2),
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                await _allowed_target(current, allowed_domains)
                try:
                    async with client.stream("GET", current) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                raise MediaFetchError(
                                    "unavailable",
                                    "The platform redirected without a destination.",
                                )
                            current = urljoin(current, location)
                            continue

                        if response.status_code in (404, 410):
                            raise MediaFetchError(
                                "unavailable",
                                "This post is unavailable. It may have been deleted "
                                "or made private.",
                            )
                        if response.status_code in (401, 403):
                            raise MediaFetchError(
                                "restricted",
                                "This post is private or the platform blocked public "
                                "access. Paste the caption or transcript instead.",
                            )
                        if response.status_code == 429:
                            raise MediaFetchError(
                                "rate_limited",
                                "The platform is temporarily rate-limiting public "
                                "requests. Try again later or paste the text.",
                            )
                        if response.status_code >= 500:
                            raise MediaFetchError(
                                "platform_unavailable",
                                "The platform is temporarily unavailable. Try again "
                                "in a moment or paste the text.",
                            )
                        if not 200 <= response.status_code < 300:
                            raise MediaFetchError(
                                "unavailable",
                                "This post could not be read from its public page.",
                            )

                        content_type = (
                            response.headers.get("content-type") or ""
                        ).lower()
                        body = await _read_limited(response, max_bytes)
                        return str(response.url), content_type, _decode_body(
                            body, content_type
                        )
                except httpx.TimeoutException as exc:
                    raise MediaFetchError(
                        "network_timeout",
                        "The platform took too long to respond. Try again or paste "
                        "the text.",
                    ) from exc
                except httpx.HTTPError as exc:
                    raise MediaFetchError(
                        "network_error",
                        "We could not reach the platform. Check the link and try "
                        "again.",
                    ) from exc
    except MediaFetchError:
        raise
    except httpx.HTTPError as exc:
        raise MediaFetchError(
            "network_error", "We could not reach the platform. Try again."
        ) from exc
    raise MediaFetchError(
        "too_many_redirects", "That link redirected too many times."
    )


async def _fetch_text(
    url: str,
    *,
    allowed_domains: tuple[str, ...],
    accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    max_bytes: int = MAX_HTML_BYTES,
) -> tuple[str, str, str]:
    """Fetch with one retry for transient platform failures."""
    last_error: Optional[MediaFetchError] = None
    for attempt in range(2):
        try:
            return await _fetch_once(
                url,
                allowed_domains=allowed_domains,
                accept=accept,
                max_bytes=max_bytes,
            )
        except MediaFetchError as exc:
            last_error = exc
            if exc.code not in {"rate_limited", "platform_unavailable", "network_timeout"}:
                raise
            if attempt == 0:
                await asyncio.sleep(0.6)
    raise last_error or MediaFetchError(
        "network_error", "We could not reach the platform."
    )


async def _fetch_json(
    url: str,
    *,
    allowed_domains: tuple[str, ...],
) -> dict[str, Any]:
    _, _, body = await _fetch_text(
        url,
        allowed_domains=allowed_domains,
        accept="application/json,text/javascript;q=0.9,*/*;q=0.1",
        max_bytes=MAX_JSON_BYTES,
    )
    try:
        data = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise MediaFetchError(
            "invalid_response", "The platform returned an unreadable public response."
        ) from exc
    if not isinstance(data, dict):
        raise MediaFetchError(
            "invalid_response", "The platform returned an unreadable public response."
        )
    return data


# ── HTML / oEmbed extraction ────────────────────────────────────────────────


def _clean_text(value: str, *, limit: int = MAX_CONTENT_CHARS) -> str:
    text = unescape(str(value or ""))
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "lxml").get_text(" ")
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = "".join(
        ch
        for ch in text
        if ch in ("\n", "\t") or ord(ch) >= 32
    )
    text = "".join(ch for ch in text if ch != "\x7f")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def _looks_generic(text: str) -> bool:
    value = " ".join((text or "").split())
    if not value:
        return True
    if len(value) < 15:
        return True
    return bool(_GENERIC_TEXT_RE.match(value))


def _meta(soup: BeautifulSoup, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for tag in soup.find_all("meta"):
        key = str(tag.get("property") or tag.get("name") or "").lower()
        if key in wanted:
            value = tag.get("content")
            if value:
                return str(value)
    return ""


def _jsonld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            objects.append(value)
            graph = value.get("@graph")
            if graph:
                walk(graph)

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            walk(json.loads(tag.string or tag.get_text() or ""))
        except (TypeError, ValueError):
            continue
    return objects


def _jsonld_value(objects: list[dict[str, Any]], key: str) -> str:
    for obj in objects:
        obj_type = obj.get("@type")
        types = obj_type if isinstance(obj_type, list) else [obj_type]
        if not any(str(item or "").lower() in _JSONLD_TYPES for item in types):
            continue
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _jsonld_author(objects: list[dict[str, Any]]) -> Optional[str]:
    for obj in objects:
        author = obj.get("author")
        if isinstance(author, dict):
            value = author.get("name") or author.get("alternateName")
            if isinstance(value, str) and value.strip():
                return value.strip()
        elif isinstance(author, list) and author:
            first = author[0]
            if isinstance(first, dict) and first.get("name"):
                return str(first["name"]).strip()
            if isinstance(first, str) and first.strip():
                return first.strip()
        elif isinstance(author, str) and author.strip():
            return author.strip()
    return None


def _embedded_caption(html: str) -> str:
    """Read the public caption Instagram/TikTok place in embed JSON.

    This is the same data their public embed widget renders. It is not a
    logged-in endpoint, and the regex deliberately accepts only the caption
    string — no broad JSON extraction.
    """
    patterns = (
        r'"edge_media_to_caption"\s*:\s*\{\s*"edges"\s*:\s*\[\s*\{\s*"node"\s*:\s*\{\s*"text"\s*:\s*("(?:\\.|[^"\\])*")',
        r'"caption"\s*:\s*\{\s*"edges"\s*:\s*\[\s*\{\s*"node"\s*:\s*\{\s*"text"\s*:\s*("(?:\\.|[^"\\])*")',
        r'"accessibility_caption"\s*:\s*("(?:\\.|[^"\\])*")',
    )
    for pattern in patterns:
        match = re.search(pattern, html or "", re.S)
        if not match:
            continue
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError):
            continue
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _embedded_timestamp(html: str) -> Optional[str]:
    match = re.search(r'"taken_at_timestamp"\s*:\s*(\d{9,12})', html or "")
    if not match:
        return None
    try:
        return datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _caption_from_metadata(text: str) -> str:
    """Pull the quoted caption out of a social platform's meta description.

    Instagram renders: `22K likes, 177 comments - shop on October 27, 2026:
    "the actual caption."`. Only the quoted caption is useful knowledge.
    """
    match = re.search(r':\s*"(.*)"\s*\.?\s*$', text or "", re.S)
    if not match:
        return ""
    return _clean_text(match.group(1))


def _author_from_metadata(
    platform: str,
    og_title: str,
    meta_description: str,
) -> Optional[str]:
    if platform not in {"instagram", "tiktok"}:
        return None
    match = re.match(r"^(.+?)\s*\(@([A-Za-z0-9._]+)\)", og_title or "")
    if match:
        display = _clean_text(match.group(1), limit=70)
        handle = match.group(2)
        if display:
            return f"{display} (@{handle})"[:100]
    handle_match = re.search(
        r"-\s*([A-Za-z0-9._]+)\s+on\s+[A-Z][a-z]+ \d{1,2}, \d{4}",
        meta_description or "",
    )
    if handle_match:
        return f"@{handle_match.group(1)}"[:100]
    return None


def _source_title(platform: str, content: str, author: Optional[str]) -> str:
    label = PLATFORM_LABELS.get(platform, "Social")
    first_line = next((line for line in content.splitlines() if line.strip()), "")
    first_line = first_line.strip()
    if len(first_line) > 90:
        first_line = first_line[:87].rstrip() + "..."
    if first_line:
        return f"{label}: {first_line}"
    if author:
        return f"{label} post by {author}"
    return f"{label} post"


def _parse_html_metadata(
    html: str,
    *,
    platform: str,
    author_hint: Optional[str] = None,
    published_hint: Optional[str] = None,
    thumbnail_hint: Optional[str] = None,
    embed: bool = False,
) -> ExtractedPost:
    soup = BeautifulSoup(html or "", "lxml")
    objects = _jsonld_objects(soup)
    og_title = _meta(soup, "og:title", "twitter:title")
    meta_description = _meta(
        soup, "og:description", "twitter:description", "description"
    )
    caption = _caption_from_metadata(meta_description)

    candidates: list[str] = []
    for value in (
        _jsonld_value(objects, "articleBody"),
        caption,
        _embedded_caption(html),
        # A raw engagement-count description adds noise when we already have
        # the quoted caption; the JSON-LD fallback helps posts without one.
        "" if caption else _jsonld_value(objects, "description"),
        "" if caption else meta_description,
    ):
        cleaned = _clean_text(value)
        if cleaned and not _looks_generic(cleaned):
            candidates.append(cleaned)

    if embed:
        caption = soup.select_one("div.Caption") or soup.select_one(".Caption")
        if caption is not None:
            cleaned = _clean_text(caption.get_text(" ", strip=True))
            if cleaned and not _looks_generic(cleaned):
                candidates.append(cleaned)

    # Keep the order stable and drop duplicate candidates.
    body_parts: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            body_parts.append(candidate)
    content = _clean_text("\n\n".join(body_parts))

    author = author_hint or _jsonld_author(objects)
    if not author:
        author = _meta(soup, "author", "article:author", "og:site_name") or None
    if author and author.strip().lower() in {"instagram", "facebook", "tiktok"}:
        author = None
    if not author:
        author = _author_from_metadata(platform, og_title, meta_description)

    title = _jsonld_value(objects, "headline")
    if not title:
        title = og_title
    if not title and soup.title and soup.title.string:
        title = str(soup.title.string)
    title = _clean_text(title, limit=200) if title else ""

    published = (
        published_hint
        or _meta(soup, "article:published_time", "datePublished", "og:published_time")
        or _embedded_timestamp(html)
        or None
    )
    if published:
        published = str(published)[:64]

    thumbnail = (
        thumbnail_hint
        or _meta(soup, "og:image", "twitter:image")
        or _jsonld_value(objects, "thumbnailUrl")
        or None
    )
    if thumbnail:
        thumb_host = urlsplit(str(thumbnail)).hostname
        if not thumb_host or urlsplit(str(thumbnail)).scheme not in ("http", "https"):
            thumbnail = None

    return ExtractedPost(
        title=title,
        content_text=content,
        author_name=author,
        published_at=published,
        thumbnail_url=thumbnail,
        extraction_method="open_graph" if not embed else "public_embed",
    )


async def _oembed(parsed: ParsedMediaUrl) -> Optional[ExtractedPost]:
    encoded = quote(parsed.url, safe="")
    if parsed.platform == "tiktok":
        endpoint = f"https://www.tiktok.com/oembed?url={encoded}"
        domains = ("tiktok.com",)
    elif parsed.platform == "instagram":
        endpoint = f"https://api.instagram.com/oembed/?url={encoded}"
        domains = ("instagram.com",)
    else:
        endpoint = f"https://www.facebook.com/plugins/post/oembed.json/?url={encoded}"
        domains = ("facebook.com",)

    data = await _fetch_json(endpoint, allowed_domains=domains)
    title = _clean_text(str(data.get("title") or ""))
    author = _clean_text(str(data.get("author_name") or ""), limit=100) or None
    thumbnail = str(data.get("thumbnail_url") or "") or None
    if thumbnail and urlsplit(thumbnail).scheme not in ("http", "https"):
        thumbnail = None

    # Instagram oEmbed commonly returns "Instagram post by X", not the caption.
    if parsed.platform == "instagram" and (
        _looks_generic(title) or title.lower().startswith("instagram post by")
    ):
        title = ""

    if not title and not author and not thumbnail:
        return None
    return ExtractedPost(
        title=_source_title(parsed.platform, title, author) if title else "",
        content_text=title,
        author_name=author,
        published_at=None,
        thumbnail_url=thumbnail,
        extraction_method="oembed",
    )


async def extract_public_post(parsed: ParsedMediaUrl) -> ExtractedPost:
    """Read permitted public metadata without authenticating.

    Strategy: oEmbed first, then the public page's OpenGraph/JSON-LD metadata.
    Instagram additionally tries its public captioned embed page when the main
    page is a login wall. If no useful caption is available, the caller asks
    the user for a manual caption/transcript.
    """
    oembed: Optional[ExtractedPost] = None
    oembed_error: Optional[MediaFetchError] = None
    try:
        oembed = await _oembed(parsed)
    except MediaFetchError as exc:
        oembed_error = exc

    if (
        oembed is not None
        and len(oembed.content_text) >= MIN_AUTO_CHARS
        and parsed.platform != "instagram"
    ):
        return oembed

    page_error: Optional[MediaFetchError] = None
    page: Optional[ExtractedPost] = None
    try:
        final_url, _, html = await _fetch_text(
            parsed.url,
            allowed_domains=PLATFORM_DOMAINS[parsed.platform],
        )
        page = _parse_html_metadata(
            html,
            platform=parsed.platform,
            author_hint=oembed.author_name if oembed else None,
            published_hint=oembed.published_at if oembed else None,
            thumbnail_hint=oembed.thumbnail_url if oembed else None,
        )
        page.final_url = final_url
    except MediaFetchError as exc:
        page_error = exc

    if parsed.platform == "instagram" and (
        page is None or len(page.content_text) < MIN_AUTO_CHARS
    ):
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", parsed.url)
        if match:
            embed_url = (
                f"https://www.instagram.com/p/{match.group(1)}/embed/captioned/"
            )
            try:
                _, _, html = await _fetch_text(
                    embed_url,
                    allowed_domains=("instagram.com",),
                )
                embedded = _parse_html_metadata(
                    html,
                    platform="instagram",
                    author_hint=oembed.author_name if oembed else None,
                    thumbnail_hint=oembed.thumbnail_url if oembed else None,
                    embed=True,
                )
                if len(embedded.content_text) > len(page.content_text if page else ""):
                    embedded.final_url = page.final_url if page else None
                    page = embedded
            except MediaFetchError:
                pass

    best = page if page and page.content_text else oembed
    if best is None:
        error = page_error or oembed_error
        if error is not None:
            raise error
        raise MediaFetchError(
            "unavailable", "This post could not be read from its public page."
        )

    content = _clean_text(best.content_text)
    if len(content) < MIN_AUTO_CHARS:
        reason = (
            "Instagram only exposes this caption to logged-in users."
            if parsed.platform == "instagram"
            else "The public page did not include enough text."
        )
        raise MediaFetchError(
            "insufficient_text",
            f"{reason} Paste the caption or upload a transcript to continue.",
        )

    author = best.author_name or (
        oembed.author_name if oembed else None
    )
    title = best.title or (oembed.title if oembed else "")
    if not title or _looks_generic(title):
        title = _source_title(parsed.platform, content, author)

    return ExtractedPost(
        title=_clean_text(title, limit=200),
        content_text=content,
        author_name=(author or None),
        published_at=best.published_at,
        thumbnail_url=best.thumbnail_url,
        extraction_method=best.extraction_method,
        final_url=best.final_url or (oembed.final_url if oembed else None),
    )


# ── Database helpers and source lifecycle ───────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _truncate(value: object, limit: int = MAX_ERROR_LENGTH) -> str:
    return str(value or "")[:limit]


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def source_to_dict(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    return {
        "id": data.get("id"),
        "workspace_id": data.get("workspace_id"),
        "agent_id": data.get("agent_id"),
        "url": data.get("url"),
        "normalized_url": data.get("normalized_url"),
        "platform": data.get("platform"),
        "provider_post_id": data.get("provider_post_id"),
        "title": data.get("title"),
        "author_name": data.get("author_name"),
        "published_at": data.get("published_at"),
        "thumbnail_url": data.get("thumbnail_url"),
        "content_text": data.get("content_text"),
        "content_hash": data.get("content_hash"),
        "status": data.get("status"),
        "extraction_method": data.get("extraction_method"),
        "error_code": data.get("error_code"),
        "error_message": data.get("error_message"),
        "chunk_count": int(data.get("chunk_count") or 0),
        "attempt_count": int(data.get("attempt_count") or 0),
        "imported_at": data.get("imported_at"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


async def _load_source(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    source_id: str,
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM social_media_sources
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (source_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    return source_to_dict(row) if row is not None else None


async def get_source(
    db: Any, *, workspace_id: str, agent_id: str, source_id: str
) -> Optional[dict[str, Any]]:
    return await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )


async def list_sources(
    db: Any, *, workspace_id: str, agent_id: str
) -> list[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM social_media_sources
           WHERE workspace_id = ? AND agent_id = ?
           ORDER BY created_at DESC""",
        (workspace_id, agent_id),
    ) as cur:
        rows = await cur.fetchall()
    return [source_to_dict(row) for row in rows]


async def create_source(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    url: str,
) -> dict[str, Any]:
    parsed = parse_media_url(url)
    async with db.execute(
        """SELECT id FROM social_media_sources
           WHERE workspace_id = ? AND agent_id = ?
             AND (
                 normalized_url = ?
                 OR (
                     provider_post_id IS NOT NULL
                     AND provider_post_id = ?
                     AND platform = ?
                 )
             )""",
        (
            workspace_id,
            agent_id,
            parsed.normalized_url,
            parsed.provider_post_id,
            parsed.platform,
        ),
    ) as cur:
        existing = await cur.fetchone()
    if existing is not None:
        raise DuplicateMediaError(
            existing["id"],
            "That post is already in this agent's media library.",
        )

    source_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO social_media_sources
           (id, workspace_id, agent_id, url, normalized_url, platform,
            provider_post_id, status, attempt_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)""",
        (
            source_id,
            workspace_id,
            agent_id,
            parsed.url,
            parsed.normalized_url,
            parsed.platform,
            parsed.provider_post_id,
            now,
            now,
        ),
    )
    await db.commit()
    source = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    assert source is not None
    return source


async def extract_source(source_id: str) -> None:
    """Background extraction. Safe to call after the source was deleted."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM social_media_sources WHERE id = ?", (source_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        source = source_to_dict(row)
        if source["status"] in {"imported", "indexing", "ready"}:
            return
        if int(source.get("attempt_count") or 0) >= MAX_EXTRACTION_ATTEMPTS:
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'awaiting_input', error_code = 'too_many_attempts',
                       error_message = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    "Automatic extraction was attempted too many times. Paste "
                    "the caption or upload a transcript to continue.",
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
            return
        await db.execute(
            """UPDATE social_media_sources
               SET status = 'extracting', attempt_count = attempt_count + 1,
                   error_code = NULL, error_message = NULL, updated_at = ?
               WHERE id = ?""",
            (_now(), source_id),
        )
        await db.commit()

    parsed = ParsedMediaUrl(
        platform=source["platform"],
        url=source["url"],
        normalized_url=source["normalized_url"],
        provider_post_id=source["provider_post_id"],
    )
    try:
        extracted = await extract_public_post(parsed)
    except MediaFetchError as exc:
        async with get_db() as db:
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'awaiting_input', error_code = ?, error_message = ?,
                       updated_at = ?
                   WHERE id = ? AND status = 'extracting'""",
                (exc.code, _truncate(exc.message), _now(), source_id),
            )
            await db.commit()
        log.info(
            "Social media extraction needs input",
            source_id=source_id,
            code=exc.code,
        )
        return
    except Exception as exc:  # pragma: no cover - defensive boundary
        log.exception("Social media extraction failed", source_id=source_id)
        async with get_db() as db:
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'failed', error_code = 'extraction_failed',
                       error_message = ?, updated_at = ?
                   WHERE id = ? AND status = 'extracting'""",
                (
                    "We could not process this link. Try again or paste the "
                    "caption manually.",
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
        return

    content = _clean_text(extracted.content_text)
    title = _clean_text(extracted.title, limit=200) or _source_title(
        source["platform"], content, extracted.author_name
    )
    content_hash = _content_hash(content)
    now = _now()

    async with get_db() as db:
        async with db.execute(
            "SELECT status FROM social_media_sources WHERE id = ?", (source_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        if row["status"] != "extracting":
            return

        normalized = source["normalized_url"]
        provider_post_id = source["provider_post_id"]
        if extracted.final_url:
            try:
                final = parse_media_url(extracted.final_url)
            except MediaValidationError:
                final = None
            if final is not None and final.platform == source["platform"]:
                normalized = final.normalized_url
                provider_post_id = final.provider_post_id or provider_post_id
                if (
                    source["url"].startswith("https://vm.")
                    or source["url"].startswith("https://vt.")
                    or source["url"].startswith("https://fb.watch")
                ):
                    stored_url = final.url
                else:
                    stored_url = source["url"]
            else:
                stored_url = source["url"]
        else:
            stored_url = source["url"]

        if normalized != source["normalized_url"]:
            async with db.execute(
                """SELECT id FROM social_media_sources
                   WHERE workspace_id = ? AND agent_id = ? AND normalized_url = ?
                     AND id <> ?""",
                (source["workspace_id"], source["agent_id"], normalized, source_id),
            ) as cur:
                duplicate = await cur.fetchone()
            if duplicate is not None:
                await db.execute(
                    """UPDATE social_media_sources
                       SET status = 'failed', error_code = 'duplicate_media',
                           error_message = ?, updated_at = ?
                       WHERE id = ? AND status = 'extracting'""",
                    (
                        "This short link points to a post already in this "
                        "agent's media library. Remove this link.",
                        now,
                        source_id,
                    ),
                )
                await db.commit()
                return

        await db.execute(
            """UPDATE social_media_sources
               SET url = ?, normalized_url = ?, provider_post_id = ?,
                   title = ?, author_name = ?, published_at = ?, thumbnail_url = ?,
                   content_text = ?, content_hash = ?, status = 'ready',
                   extraction_method = ?, error_code = NULL, error_message = NULL,
                   updated_at = ?
               WHERE id = ? AND status = 'extracting'""",
            (
                stored_url,
                normalized,
                provider_post_id,
                title,
                extracted.author_name,
                extracted.published_at,
                extracted.thumbnail_url,
                content,
                content_hash,
                extracted.extraction_method,
                now,
                source_id,
            ),
        )
        await db.commit()
    log.info(
        "Social media extracted",
        source_id=source_id,
        platform=source["platform"],
        method=extracted.extraction_method,
        chars=len(content),
    )


async def update_source_text(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    source_id: str,
    content_text: str,
    title: Optional[str] = None,
) -> dict[str, Any]:
    source = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    if source is None:
        raise MediaValidationError("not_found", "Media source not found.")
    if source["status"] in {"extracting", "indexing"}:
        raise MediaValidationError(
            "busy", "Wait for the current media job to finish before editing."
        )
    if source["status"] == "imported":
        raise MediaValidationError(
            "already_imported",
            "This source is already imported. Remove and re-import it to change "
            "its text.",
        )

    text = _clean_text(content_text, limit=MAX_MANUAL_CHARS)
    if len(text) < MIN_MANUAL_CHARS:
        raise MediaValidationError(
            "insufficient_text",
            f"Paste at least {MIN_MANUAL_CHARS} characters of caption or transcript.",
        )

    digest = _content_hash(text)
    async with db.execute(
        """SELECT id FROM social_media_sources
           WHERE agent_id = ? AND content_hash = ? AND id <> ?
             AND status IN ('ready', 'indexing', 'imported')
           LIMIT 1""",
        (agent_id, digest, source_id),
    ) as cur:
        duplicate = await cur.fetchone()
    if duplicate is not None:
        raise DuplicateMediaError(
            duplicate["id"],
            "Another media source in this agent has the same text.",
        )

    final_title = _clean_text(title or "", limit=200)
    if not final_title:
        final_title = source.get("title") or _source_title(
            source["platform"], text, source.get("author_name")
        )
    await db.execute(
        """UPDATE social_media_sources
           SET title = ?, content_text = ?, content_hash = ?, status = 'ready',
               extraction_method = 'manual', error_code = NULL,
               error_message = NULL, updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (final_title, text, digest, _now(), source_id, workspace_id, agent_id),
    )
    await db.commit()
    updated = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    assert updated is not None
    return updated


async def prepare_retry(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    source_id: str,
) -> tuple[dict[str, Any], bool]:
    """Reset a failed source. Returns (source, extraction_needed)."""
    source = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    if source is None:
        raise MediaValidationError("not_found", "Media source not found.")
    if source["status"] in {"extracting", "indexing", "imported"}:
        raise MediaValidationError(
            "invalid_status", "This source cannot be retried right now."
        )
    if source["status"] == "failed" and source.get("content_text"):
        await db.execute(
            """UPDATE social_media_sources
               SET status = 'ready', error_code = NULL, error_message = NULL,
                   updated_at = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (_now(), source_id, workspace_id, agent_id),
        )
        await db.commit()
        updated = await _load_source(
            db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
        )
        assert updated is not None
        return updated, False

    await db.execute(
        """UPDATE social_media_sources
           SET status = 'pending', error_code = NULL, error_message = NULL,
               updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (_now(), source_id, workspace_id, agent_id),
    )
    await db.commit()
    updated = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    assert updated is not None
    return updated, True


async def claim_sources_for_sync(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    source_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Validate duplicates, claim ready sources, and return them as indexing."""
    if source_ids is not None:
        unique_ids = list(dict.fromkeys(source_ids))
        if not unique_ids:
            raise MediaValidationError(
                "nothing_to_import", "Select at least one media source to sync."
            )
        placeholders = ",".join("?" * len(unique_ids))
        async with db.execute(
            f"""SELECT * FROM social_media_sources
                WHERE workspace_id = ? AND agent_id = ?
                  AND id IN ({placeholders})""",
            (workspace_id, agent_id, *unique_ids),
        ) as cur:
            rows = await cur.fetchall()
        by_id = {row["id"]: _row_dict(row) for row in rows}
        if len(by_id) != len(unique_ids):
            raise MediaValidationError("not_found", "Media source not found.")
        selected = [by_id[source_id] for source_id in unique_ids]
        for row in selected:
            if row.get("status") != "ready":
                raise MediaValidationError(
                    "invalid_status",
                    "Only sources that are ready to import can be synced.",
                )
    else:
        async with db.execute(
            """SELECT * FROM social_media_sources
               WHERE workspace_id = ? AND agent_id = ? AND status = 'ready'
               ORDER BY created_at""",
            (workspace_id, agent_id),
        ) as cur:
            selected = [_row_dict(row) for row in await cur.fetchall()]
        if not selected:
            raise MediaValidationError(
                "nothing_to_import",
                "Add a link or finish reviewing a media source before syncing.",
            )

    # Reject identical text before claiming anything, so a batch never
    # partially imports and then discovers a duplicate.
    selected_hashes: dict[str, str] = {}
    for row in selected:
        digest = row.get("content_hash")
        if not digest:
            raise MediaValidationError(
                "insufficient_text", "A selected source has no text to import."
            )
        if digest in selected_hashes:
            raise DuplicateMediaError(
                selected_hashes[digest],
                "Two selected links contain the same text. Remove one before syncing.",
            )
        selected_hashes[digest] = row["id"]
        async with db.execute(
            """SELECT id FROM social_media_sources
               WHERE agent_id = ? AND content_hash = ? AND id <> ?
                 AND status IN ('ready', 'indexing', 'imported')
               LIMIT 1""",
            (agent_id, digest, row["id"]),
        ) as cur:
            existing = await cur.fetchone()
        if existing is not None:
            raise DuplicateMediaError(
                existing["id"],
                "This text is already imported into this agent.",
            )

    claimed: list[dict[str, Any]] = []
    now = _now()
    for row in selected:
        cur = await db.execute(
            """UPDATE social_media_sources
               SET status = 'indexing', error_code = NULL, error_message = NULL,
                   updated_at = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?
                 AND status = 'ready'""",
            (now, row["id"], workspace_id, agent_id),
        )
        if getattr(cur, "rowcount", 1) == 1:
            claimed.append(row["id"])
    await db.commit()

    if not claimed:
        raise MediaValidationError(
            "invalid_status", "Those media sources are no longer ready to sync."
        )
    placeholders = ",".join("?" * len(claimed))
    async with db.execute(
        f"SELECT * FROM social_media_sources WHERE id IN ({placeholders})",
        claimed,
    ) as cur:
        rows = await cur.fetchall()
    return [source_to_dict(row) for row in rows]


# ── Indexing ────────────────────────────────────────────────────────────────


async def _prepare_virtual_document(
    db: Any,
    *,
    source: dict[str, Any],
    title: str,
) -> None:
    now = _now()
    filename = title or source["url"]
    source_id = source["id"]
    workspace_id = source["workspace_id"]

    async with db.execute(
        "SELECT id FROM workspace_documents WHERE id = ?", (source_id,)
    ) as cur:
        exists = await cur.fetchone() is not None
    if exists:
        await db.execute(
            """UPDATE workspace_documents
               SET filename = ?, status = 'processing', chunk_count = 0,
                   file_path = '', file_type = 'social', size_bytes = 0
               WHERE id = ? AND workspace_id = ?""",
            (filename, source_id, workspace_id),
        )
    else:
        await db.execute(
            """INSERT INTO workspace_documents
               (id, workspace_id, filename, file_path, file_type, size_bytes,
                status, chunk_count, created_at)
               VALUES (?, ?, ?, '', 'social', 0, 'processing', 0, ?)""",
            (source_id, workspace_id, filename, now),
        )

    async with db.execute(
        "SELECT id FROM documents WHERE id = ?", (source_id,)
    ) as cur:
        exists = await cur.fetchone() is not None
    if exists:
        await db.execute(
            """UPDATE documents
               SET filename = ?, upload_date = ?, total_pages = 1,
                   file_size = 0, status = 'ready'
               WHERE id = ?""",
            (filename, now, source_id),
        )
    else:
        await db.execute(
            """INSERT INTO documents
               (id, filename, upload_date, total_pages, file_size, status)
               VALUES (?, ?, ?, 1, 0, 'ready')""",
            (source_id, filename, now),
        )
    await db.commit()


async def remove_source_chunks(
    db: Any, *, source_id: str, workspace_id: str
) -> None:
    await vector_store.delete_embeddings_for_document(db, source_id)
    await db.execute(
        "DELETE FROM chunks WHERE workspace_id = ? AND (document_id = ? OR doc_id = ?)",
        (workspace_id, source_id, source_id),
    )
    await db.execute(
        """DELETE FROM workspace_documents
           WHERE id = ? AND workspace_id = ? AND file_type = 'social'""",
        (source_id, workspace_id),
    )
    await db.execute(
        """DELETE FROM documents
           WHERE id = ?
             AND NOT EXISTS (SELECT 1 FROM workspace_documents WHERE id = ?)""",
        (source_id, source_id),
    )
    await db.commit()


async def _source_exists(db: Any, source_id: str, status: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM social_media_sources WHERE id = ? AND status = ?",
        (source_id, status),
    ) as cur:
        return await cur.fetchone() is not None


async def index_source(source_id: str) -> None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM social_media_sources WHERE id = ?", (source_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        source = _row_dict(row)
        if source.get("status") != "indexing":
            return
        content = _clean_text(source.get("content_text") or "")
        if len(content) < MIN_MANUAL_CHARS:
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'awaiting_input', error_code = 'insufficient_text',
                       error_message = ?, updated_at = ?
                   WHERE id = ? AND status = 'indexing'""",
                (
                    "There is no text to index. Paste the caption or transcript.",
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
            return

        title = source.get("title") or _source_title(
            source.get("platform") or "social",
            content,
            source.get("author_name"),
        )
        header_parts = [
            f"Imported {PLATFORM_LABELS.get(source.get('platform'), 'social media')} post",
            f"Original URL: {source.get('url')}",
        ]
        if source.get("author_name"):
            header_parts.append(f"Author: {source['author_name']}")
        if source.get("published_at"):
            header_parts.append(f"Published: {source['published_at']}")
        header_parts.append("Content:")
        index_text = "\n".join(header_parts) + "\n\n" + content
        index_text = index_text[: MAX_CONTENT_CHARS + 500]

        pages = [
            PageContent(
                page_number=1,
                text=index_text,
                char_count=len(index_text),
            )
        ]
        try:
            chunks = await asyncio.to_thread(chunk_document, pages)
            if not chunks:
                raise ValueError("The imported post produced no chunks.")
            embeddings = await asyncio.to_thread(
                embed_texts, [chunk.text for chunk in chunks]
            )
        except Exception:
            log.exception("Social media embedding failed", source_id=source_id)
            await remove_source_chunks(db, source_id=source_id, workspace_id=source["workspace_id"])
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'failed', error_code = 'indexing_failed',
                       error_message = ?, chunk_count = 0, updated_at = ?
                   WHERE id = ? AND status = 'indexing'""",
                (
                    "We could not index this post. Try again; the link and its "
                    "text are still saved.",
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
            return

        if not await _source_exists(db, source_id, "indexing"):
            return

        await _prepare_virtual_document(db, source=source, title=title)
        await vector_store.delete_embeddings_for_document(db, source_id)
        await db.execute(
            "DELETE FROM chunks WHERE workspace_id = ? AND (document_id = ? OR doc_id = ?)",
            (source["workspace_id"], source_id, source_id),
        )
        await db.commit()

        try:
            chunk_ids = await index_chunks(
                db,
                source_id,
                chunks,
                embeddings,
                metadata={
                    "workspace_id": source["workspace_id"],
                    "doc_id": source_id,
                    "agent_id": source["agent_id"],
                    "filename": title,
                    "source_type": "social_media",
                    "source_url": source["url"],
                },
            )
        except Exception:
            log.exception("Social media index write failed", source_id=source_id)
            await remove_source_chunks(db, source_id=source_id, workspace_id=source["workspace_id"])
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'failed', error_code = 'indexing_failed',
                       error_message = ?, chunk_count = 0, updated_at = ?
                   WHERE id = ? AND status = 'indexing'""",
                (
                    "We could not index this post. Try again; your saved text is "
                    "still available.",
                    _now(),
                    source_id,
                ),
            )
            await db.commit()
            return

        if not await _source_exists(db, source_id, "indexing"):
            await remove_source_chunks(
                db, source_id=source_id, workspace_id=source["workspace_id"]
            )
            return

        now = _now()
        await db.execute(
            """UPDATE workspace_documents
               SET filename = ?, status = 'ready', chunk_count = ?
               WHERE id = ? AND workspace_id = ?""",
            (title, len(chunk_ids), source_id, source["workspace_id"]),
        )
        await db.execute(
            "UPDATE documents SET filename = ?, status = 'ready' WHERE id = ?",
            (title, source_id),
        )
        await db.execute(
            """UPDATE social_media_sources
               SET status = 'imported', chunk_count = ?, imported_at = ?,
                   error_code = NULL, error_message = NULL, updated_at = ?
               WHERE id = ? AND status = 'indexing'""",
            (len(chunk_ids), now, now, source_id),
        )
        await db.commit()
    log.info("Social media source imported", source_id=source_id)


async def index_sources(source_ids: list[str]) -> None:
    for source_id in source_ids:
        try:
            await index_source(source_id)
        except Exception:  # pragma: no cover - one source must not stop the batch
            log.exception("Social media import job failed", source_id=source_id)


async def delete_source(
    db: Any,
    *,
    workspace_id: str,
    agent_id: str,
    source_id: str,
) -> bool:
    source = await _load_source(
        db, workspace_id=workspace_id, agent_id=agent_id, source_id=source_id
    )
    if source is None:
        return False
    if source["status"] in {"extracting", "indexing"}:
        raise MediaValidationError(
            "busy", "Wait for the current media job to finish before removing it."
        )
    await remove_source_chunks(
        db, source_id=source_id, workspace_id=workspace_id
    )
    await db.execute(
        """DELETE FROM social_media_sources
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (source_id, workspace_id, agent_id),
    )
    await db.commit()
    return True


async def remove_all_for_agent(db: Any, *, agent_id: str) -> int:
    """Clean up virtual documents before an agent row is deleted."""
    async with db.execute(
        "SELECT id, workspace_id FROM social_media_sources WHERE agent_id = ?",
        (agent_id,),
    ) as cur:
        rows = await cur.fetchall()
    for row in rows:
        await remove_source_chunks(
            db, source_id=row["id"], workspace_id=row["workspace_id"]
        )
    await db.execute("DELETE FROM social_media_sources WHERE agent_id = ?", (agent_id,))
    await db.commit()
    return len(rows)


async def recover_stale_imports() -> int:
    """Mark in-flight imports from a stopped process as failed.

    Rows otherwise stay `extracting`/`indexing` forever. Partial chunks and
    virtual documents are removed, but the source and any saved text remain so
    the owner can press Retry.
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT id, workspace_id FROM social_media_sources
               WHERE status IN ('pending', 'extracting', 'indexing')"""
        ) as cur:
            rows = await cur.fetchall()
        for row in rows:
            await remove_source_chunks(
                db, source_id=row["id"], workspace_id=row["workspace_id"]
            )
            await db.execute(
                """UPDATE social_media_sources
                   SET status = 'failed', error_code = 'interrupted',
                       error_message = ?, chunk_count = 0, updated_at = ?
                   WHERE id = ?""",
                (
                    "The import was interrupted by a server restart. Press Retry "
                    "to continue.",
                    _now(),
                    row["id"],
                ),
            )
        await db.commit()
    if rows:
        log.info("Recovered stale social media imports", count=len(rows))
    return len(rows)


async def media_usage(
    db: Any, *, workspace: dict, agent_id: str
) -> dict[str, int]:
    plan = await plan_service.plan_for_workspace(db, workspace)
    used = await plan_service.social_media_sources_used(db, agent_id)
    return {"used": used, "limit": plan.max_social_media_sources}
