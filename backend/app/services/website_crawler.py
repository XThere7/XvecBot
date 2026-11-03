"""
services/website_crawler.py

Polite, SSRF-safe HTML crawler for Website-to-Knowledge.

Properties:
  * no JavaScript execution — only server-rendered HTML is indexed;
  * robots.txt is respected for the crawler user-agent and ``*``;
  * sitemap.xml (including sitemap indexes) is preferred when present;
  * otherwise same-site links are followed breadth-first;
  * every URL is capped at 50 pages, 5 MB, 15 seconds, and 2 retries;
  * every request/redirect is validated by ``core.ssrf_guard``.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Iterable, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from ..core import ssrf_guard
from ..core.logging import get_logger

log = get_logger(__name__)

MAX_PAGES_PER_SOURCE = 50
MAX_RESPONSE_SIZE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 2
MAX_REDIRECTS = 5
MAX_SITEMAPS = 5
MAX_URL_LENGTH = 2048
USER_AGENT = "XvecBot-Crawler/1.0"

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
_RESOURCE_EXTENSIONS = {
    ".7z", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot", ".gif",
    ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json", ".m4a", ".m4v", ".mov",
    ".mp3", ".mp4", ".mpeg", ".pdf", ".png", ".ppt", ".pptx", ".rar", ".rss",
    ".svg", ".tar", ".tif", ".tiff", ".ttf", ".txt", ".wav", ".webm", ".webp",
    ".woff", ".woff2", ".xls", ".xlsx", ".xml", ".zip",
}
_NOISE_CLASS_RE = re.compile(
    r"(?:^|[\s_-])("
    r"nav|navbar|navigation|menu|sidebar|side-bar|footer|header|cookie|"
    r"consent|banner|advert|advertisement|ads?|social|share|breadcrumb|"
    r"skip|popup|modal|newsletter"
    r")(?:$|[\s_-])",
    re.IGNORECASE,
)
_NOISE_ROLES = {
    "navigation",
    "banner",
    "contentinfo",
    "complementary",
    "search",
    "dialog",
}


class CrawlError(Exception):
    """Raised for a non-fatal per-page or per-resource crawl failure."""


def build_client() -> httpx.AsyncClient:
    """Shared HTTP client configuration for crawling."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        follow_redirects=False,
        # A proxy would bypass the direct DNS/IP checks in ssrf_guard.
        trust_env=False,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )


def normalise_url(url: str) -> str:
    """Canonical URL form used for de-duplication and storage."""
    raw = (url or "").strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").rstrip(".").lower()
    if not scheme or not host:
        return raw

    try:
        port = parsed.port
    except ValueError:
        port = None
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    host_port = host if ":" not in host else f"[{host}]"
    if port is not None and not default_port:
        host_port = f"{host_port}:{port}"

    # Keep a distinguishing trailing slash: ``/blog/`` and ``/blog`` can be
    # different resources, and relative links inside a directory must resolve
    # against the URL that was actually fetched.
    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)

    return urlunsplit((scheme, host_port, path, parsed.query, ""))


def _same_site(first: str, second: str) -> bool:
    a = (urlsplit(first).hostname or "").lower().removeprefix("www.")
    b = (urlsplit(second).hostname or "").lower().removeprefix("www.")
    return bool(a and b and a == b)


def _has_resource_extension(url: str) -> bool:
    path = (urlsplit(url).path or "").lower()
    return any(path.endswith(ext) for ext in _RESOURCE_EXTENSIONS)


def _decode_body(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    if body.startswith(b"\xef\xbb\xbf"):
        charset = "utf-8-sig"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > limit:
                raise CrawlError("Page is too large to index.")
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise CrawlError("Page is too large to index.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _get_bytes_once(
    url: str,
    *,
    session: httpx.AsyncClient,
    allowed_content_types: Optional[tuple[str, ...]] = None,
    max_bytes: int = MAX_RESPONSE_SIZE_BYTES,
) -> tuple[str, str, bytes]:
    """One fetch attempt, with manual redirect validation."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            await ssrf_guard.validate_url_async(current, resolve_dns=True)
        except HTTPException as exc:
            raise CrawlError(str(exc.detail)) from exc

        try:
            async with session.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise CrawlError("Redirected without a destination.")
                    destination = urljoin(current, location)
                    try:
                        await ssrf_guard.safe_follow_redirect(destination)
                    except HTTPException as exc:
                        raise CrawlError(str(exc.detail)) from exc
                    if not _same_site(destination, url):
                        raise CrawlError("Redirected to a different site.")
                    current = destination
                    continue

                if response.status_code < 200 or response.status_code >= 300:
                    raise CrawlError(f"Page returned HTTP {response.status_code}.")

                content_type = (response.headers.get("content-type") or "").lower()
                if allowed_content_types and not any(
                    content_type.startswith(value) for value in allowed_content_types
                ):
                    raise CrawlError("URL did not return an HTML page.")

                body = await _read_limited(response, max_bytes)
                return str(response.url), content_type, body
        except CrawlError:
            raise
        except httpx.HTTPError as exc:
            raise CrawlError(
                f"Could not fetch the page ({type(exc).__name__})."
            ) from exc

    raise CrawlError("Too many redirects.")


def _retryable(exc: CrawlError) -> bool:
    message = str(exc)
    status_match = re.search(r"HTTP (\d{3})", message)
    if status_match:
        code = int(status_match.group(1))
        return code == 429 or code >= 500
    return not any(
        marker in message
        for marker in (
            "restricted address",
            "not allowed",
            "did not return an HTML page",
            "too large",
            "too little text",
            "no HTML",
            "Too many redirects",
            "Invalid sitemap",
            "Unsupported sitemap",
            "different site",
        )
    )


async def _get_bytes(
    url: str,
    *,
    session: httpx.AsyncClient,
    allowed_content_types: Optional[tuple[str, ...]] = None,
    max_bytes: int = MAX_RESPONSE_SIZE_BYTES,
) -> tuple[str, str, bytes]:
    """Fetch with up to MAX_RETRIES retries for transient failures."""
    last_error: Optional[CrawlError] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await _get_bytes_once(
                url,
                session=session,
                allowed_content_types=allowed_content_types,
                max_bytes=max_bytes,
            )
        except CrawlError as exc:
            last_error = exc
            if attempt >= MAX_RETRIES or not _retryable(exc):
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    raise last_error or CrawlError("Could not fetch the page.")


async def _fetch_resource(
    url: str,
    *,
    session: httpx.AsyncClient,
    max_bytes: int = MAX_RESPONSE_SIZE_BYTES,
) -> str:
    """Fetch robots.txt / sitemap XML as text."""
    _, content_type, body = await _get_bytes(
        url, session=session, allowed_content_types=None, max_bytes=max_bytes
    )
    return _decode_body(body, content_type)


def _normalise_text(value: str) -> str:
    lines: list[str] = []
    for raw_line in (value or "").replace("\xa0", " ").splitlines():
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def _looks_like_noise(tag) -> bool:
    role = (tag.get("role") or "").strip().lower()
    if role in _NOISE_ROLES:
        return True
    classes = " ".join(tag.get("class") or [])
    element_id = tag.get("id") or ""
    value = f"{classes} {element_id}".strip()
    return bool(value and _NOISE_CLASS_RE.search(value))


def extract_text(html: str, base_url: str) -> tuple[str, str]:
    """
    Turn a server-rendered HTML page into (title, clean_text).

    Navigation, headers, footers, forms, scripts, styles, cookie banners and
    ad slots are removed before text extraction. Raises CrawlError when fewer
    than 100 characters of useful text remain.
    """
    if not html or not html.strip():
        raise CrawlError("Page contains no HTML.")

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(
        ["script", "style", "noscript", "template", "svg", "canvas", "iframe",
         "object", "embed", "form", "nav", "footer", "header", "aside"]
    ):
        tag.decompose()

    for tag in list(soup.find_all(True)):
        if getattr(tag, "attrs", None) is None:
            continue
        if _looks_like_noise(tag):
            tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = " ".join(str(soup.title.string).split())
    if not title:
        heading = soup.find("h1")
        if heading is not None:
            title = " ".join(heading.get_text(" ", strip=True).split())
    if not title:
        parsed = urlsplit(base_url)
        title = parsed.hostname or base_url

    # Prefer the semantic content container, but fall back to <body> when a
    # short <main> would silently drop the actual article.
    candidates = []
    for selector in ("main", "[role='main']", "article", "body"):
        candidates.extend(soup.select(selector))
    if not candidates:
        candidates = [soup]

    best = ""
    for candidate in candidates:
        text = _normalise_text(candidate.get_text("\n", strip=True))
        if len(text) >= 100:
            best = text
            break
        if len(text) > len(best):
            best = text

    if len(best) < 100:
        raise CrawlError("Page contains too little text.")
    return title, best


async def _extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = urljoin(base_url, href)
        normalized = normalise_url(absolute)
        if normalized.startswith(("http://", "https://")):
            links.append(normalized)
    return links


def _robots_for(url: str, robots_text: str) -> Optional[RobotFileParser]:
    if not robots_text:
        return None
    parser = RobotFileParser()
    parser.set_url(url)
    try:
        parser.parse(robots_text.splitlines())
    except Exception:
        return None
    return parser


def _sitemap_urls(robots_text: str, root_url: str) -> list[str]:
    urls: list[str] = []
    for line in (robots_text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "sitemap" and value.strip():
            candidate = normalise_url(urljoin(root_url, value.strip()))
            if _same_site(candidate, root_url):
                urls.append(candidate)
    parsed = urlsplit(root_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    urls.append(f"{origin}/sitemap.xml")
    return list(dict.fromkeys(urls))


def _candidate_allowed(
    url: str,
    *,
    root_url: str,
    robots: Optional[RobotFileParser],
) -> bool:
    candidate = normalise_url(url)
    if not candidate.startswith(("http://", "https://")):
        return False
    if len(candidate) > MAX_URL_LENGTH:
        return False
    if not _same_site(candidate, root_url):
        return False
    if _has_resource_extension(candidate):
        return False
    if robots is not None and not robots.can_fetch(USER_AGENT, candidate):
        return False
    return True


def _parse_sitemap(xml_text: str) -> tuple[str, list[str]]:
    """Return (kind, locs) where kind is 'urlset' or 'sitemapindex'."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise CrawlError("Invalid sitemap XML.") from exc
    kind = root.tag.rsplit("}", 1)[-1].lower()
    if kind not in ("urlset", "sitemapindex"):
        raise CrawlError("Unsupported sitemap format.")
    locations: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text:
            value = element.text.strip()
            if value:
                locations.append(value)
    return kind, locations


async def _collect_sitemap_pages(
    sitemap_url: str,
    *,
    session: httpx.AsyncClient,
    root_url: str,
    robots: Optional[RobotFileParser],
    seen_sitemaps: set[str],
    seen_pages: set[str],
    pages: list[str],
    max_pages: int,
) -> None:
    if len(seen_sitemaps) >= MAX_SITEMAPS or len(pages) >= max_pages:
        return
    normalized = normalise_url(sitemap_url)
    if normalized in seen_sitemaps or not _same_site(normalized, root_url):
        return
    seen_sitemaps.add(normalized)

    try:
        text = await _fetch_resource(normalized, session=session)
        kind, locations = _parse_sitemap(text)
    except CrawlError as exc:
        log.debug("Sitemap skipped", url=normalized, error=str(exc))
        return

    if kind == "sitemapindex":
        for location in locations:
            await _collect_sitemap_pages(
                urljoin(normalized, location),
                session=session,
                root_url=root_url,
                robots=robots,
                seen_sitemaps=seen_sitemaps,
                seen_pages=seen_pages,
                pages=pages,
                max_pages=max_pages,
            )
            if len(pages) >= max_pages:
                return
        return

    for location in locations:
        candidate = normalise_url(urljoin(normalized, location))
        if not _candidate_allowed(candidate, root_url=root_url, robots=robots):
            continue
        if candidate in seen_pages:
            continue
        try:
            await ssrf_guard.validate_url_async(candidate, resolve_dns=False)
        except HTTPException:
            continue
        seen_pages.add(candidate)
        pages.append(candidate)
        if len(pages) >= max_pages:
            return


async def discover_pages(
    root_url: str,
    *,
    max_pages: int = MAX_PAGES_PER_SOURCE,
    session: Optional[httpx.AsyncClient] = None,
) -> list[str]:
    """
    Discover up to ``max_pages`` crawlable pages for a site.

    Order: robots.txt rules -> sitemap(s) -> same-site link crawling.
    """
    max_pages = max(1, min(max_pages, MAX_PAGES_PER_SOURCE))
    root = normalise_url(root_url)
    await ssrf_guard.validate_url_async(root, resolve_dns=True)

    own_session = session is None
    client = session or build_client()
    try:
        parsed = urlsplit(root)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_text = ""
        try:
            robots_text = await _fetch_resource(
                f"{origin}/robots.txt", session=client, max_bytes=512 * 1024
            )
        except CrawlError as exc:
            log.debug("robots.txt unavailable", url=root, error=str(exc))

        robots = _robots_for(f"{origin}/robots.txt", robots_text)

        pages: list[str] = []
        seen_pages: set[str] = set()
        root_allowed = _candidate_allowed(root, root_url=root, robots=robots)
        if root_allowed:
            pages.append(root)
            seen_pages.add(root)

        seen_sitemaps: set[str] = set()
        for sitemap_url in _sitemap_urls(robots_text, root):
            await _collect_sitemap_pages(
                sitemap_url,
                session=client,
                root_url=root,
                robots=robots,
                seen_sitemaps=seen_sitemaps,
                seen_pages=seen_pages,
                pages=pages,
                max_pages=max_pages,
            )
            if len(pages) >= max_pages:
                break

        if not pages:
            log.info("No sitemap pages found; crawling links", url=root)

        # A sitemap can be incomplete or absent. If it produced fewer than one
        # page beyond the root, fall back to breadth-first link discovery.
        if len(pages) <= 1:
            queue: list[str] = [root] if root_allowed else []
            crawled: set[str] = set()
            while queue and len(pages) < max_pages:
                current = queue.pop(0)
                if current in crawled:
                    continue
                crawled.add(current)
                if current != root and not _candidate_allowed(
                    current, root_url=root, robots=robots
                ):
                    continue

                try:
                    final_url, content_type, body = await _get_bytes(
                        current,
                        session=client,
                        allowed_content_types=_HTML_CONTENT_TYPES,
                    )
                except CrawlError as exc:
                    log.debug("Discovery fetch failed", url=current, error=str(exc))
                    continue

                if current != root and current not in seen_pages:
                    seen_pages.add(current)
                    pages.append(current)
                if len(pages) >= max_pages:
                    break

                html = _decode_body(body, content_type)
                for link in await _extract_links(html, final_url):
                    if len(queue) + len(crawled) >= max_pages * 8:
                        break
                    if link in seen_pages or link in crawled or link in queue:
                        continue
                    if _candidate_allowed(link, root_url=root, robots=robots):
                        queue.append(link)

                if current != root or queue:
                    await asyncio.sleep(REQUEST_DELAY_SECONDS)

        # Return root first when robots allows it; a sitemap may put the
        # homepage later, and stable ordering makes syncs deterministic.
        ordered = [root] + [page for page in pages if page != root] if root_allowed else pages
        return ordered[:max_pages]
    finally:
        if own_session:
            await client.aclose()


async def fetch_page(
    url: str,
    *,
    session: httpx.AsyncClient,
) -> tuple[str, str, str]:
    """
    Fetch and clean one HTML page.

    Returns (final_url, page_title, clean_text). Raises CrawlError on failure,
    oversized/non-HTML responses, or pages with less than 100 useful chars.
    """
    final_url, content_type, body = await _get_bytes(
        url, session=session, allowed_content_types=_HTML_CONTENT_TYPES
    )
    html = _decode_body(body, content_type)
    title, clean_text = extract_text(html, final_url)
    return final_url, title, clean_text
