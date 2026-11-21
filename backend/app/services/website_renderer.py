"""
services/website_renderer.py
Optional JavaScript rendering for client-rendered websites.

The static crawler intentionally does not execute JavaScript. Some legitimate
sites (including Vite/React SPAs) serve only an empty shell plus a script. When
``WEBSITE_JS_RENDER_ENABLED`` is true and Playwright is installed, this module
renders such a page in headless Chromium and returns the resulting DOM.

Security boundary:
  * the document and every subresource are validated by ``ssrf_guard``;
  * only requests to the submitted site (same host, ``www`` insensitive) are
    allowed — all third-party, private and non-HTTP requests are aborted;
  * images, fonts, media and downloads are blocked because text extraction does
    not need them;
  * service workers are disabled and popups/dialogs are dismissed;
  * the browser is closed at the end of each sync.

This reduces the SSRF surface substantially, but running any browser against
untrusted HTML remains a higher-risk operation than static parsing. Production
deployments should keep the renderer in a dedicated, resource-limited container
when the infrastructure supports it.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlsplit

from fastapi import HTTPException

from ..core import ssrf_guard
from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "other"}
_BLOCKED_SCHEMES = ("data:", "blob:")


class RenderError(Exception):
    """A safe, user-facing rendering failure."""


def _same_site(first: str, second: str) -> bool:
    a = (urlsplit(first).hostname or "").lower().removeprefix("www.")
    b = (urlsplit(second).hostname or "").lower().removeprefix("www.")
    return bool(a and b and a == b)


class JavaScriptRenderer:
    def __init__(
        self,
        root_url: str,
        *,
        max_renders: int,
        timeout_ms: int,
        browser_path: str,
    ) -> None:
        self.root_url = root_url
        self.max_renders = max_renders
        self.timeout_ms = timeout_ms
        self.browser_path = browser_path
        self._playwright = None
        self._browser = None
        self._renders = 0

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_args = [
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-sync",
            "--mute-audio",
            "--no-first-run",
        ]
        if settings.website_browser_no_sandbox:
            launch_args.append("--no-sandbox")
        kwargs = {
            "headless": True,
            "args": launch_args,
            # Be explicit: Playwright defaults Chromium's sandbox off, which is
            # easy to miss. Enable it unless the operator deliberately opted out.
            "chromium_sandbox": not settings.website_browser_no_sandbox,
        }
        if self.browser_path:
            kwargs["executable_path"] = self.browser_path
        self._browser = await self._playwright.chromium.launch(**kwargs)

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

    async def _route(self, route) -> None:
        request = route.request
        url = request.url
        if url.startswith(_BLOCKED_SCHEMES):
            await route.continue_()
            return
        if not url.startswith(("http://", "https://")):
            await route.abort()
            return
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        if not _same_site(url, self.root_url):
            await route.abort()
            return
        try:
            await ssrf_guard.validate_url_async(url, resolve_dns=True)
        except HTTPException:
            await route.abort()
            return
        await route.continue_()

    async def render(self, url: str) -> tuple[str, str]:
        if self._browser is None:
            raise RenderError("JavaScript rendering is not available.")
        if self._renders >= self.max_renders:
            raise RenderError("JavaScript rendering limit reached for this scan.")
        self._renders += 1

        context = await self._browser.new_context(
            user_agent="XvecBot-Crawler/1.0",
            java_script_enabled=True,
            accept_downloads=False,
            service_workers="block",
            ignore_https_errors=False,
        )
        page = await context.new_page()

        async def dismiss(dialog) -> None:
            try:
                await dialog.dismiss()
            except Exception:
                pass

        page.on("dialog", dismiss)
        await page.route("**/*", self._route)
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=min(8000, self.timeout_ms)
                )
            except Exception:
                # Analytics and long-polling can keep the network busy forever;
                # the DOM is still usable.
                pass
            await page.wait_for_timeout(750)
            final_url = page.url
            if not _same_site(final_url, self.root_url):
                raise RenderError("The page redirected to a different site.")
            try:
                await ssrf_guard.validate_url_async(final_url, resolve_dns=True)
            except HTTPException as exc:
                raise RenderError(str(exc.detail)) from exc
            html = await page.content()
            return final_url, html
        except RenderError:
            raise
        except Exception as exc:
            log.warning("JavaScript render failed", error=type(exc).__name__)
            raise RenderError("The page could not be rendered.") from exc
        finally:
            await context.close()


async def create_renderer(root_url: str) -> Optional[JavaScriptRenderer]:
    """Start a renderer when enabled and available; otherwise return None."""
    if not settings.website_js_render_enabled:
        return None
    try:
        renderer = JavaScriptRenderer(
            root_url,
            max_renders=max(1, settings.website_render_max_pages),
            timeout_ms=max(3000, settings.website_render_timeout_ms),
            browser_path=(settings.website_browser_path or "").strip(),
        )
        await renderer.start()
        return renderer
    except Exception as exc:
        log.warning(
            "JavaScript renderer unavailable; static extraction will be used",
            error=type(exc).__name__,
        )
        return None
