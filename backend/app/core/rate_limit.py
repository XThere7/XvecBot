"""
core/rate_limit.py (Phase 4)
Minimal in-memory fixed-window rate limiter, env-gated and narrowly scoped.

Scope: /auth/* (login/register brute force) and /public/* (widget abuse).
Everything else (dashboard JWT routes, health) is unthrottled.

Defaults keep local dev and the test suite untouched: disabled unless
RATE_LIMIT_ENABLED=true (prod compose sets it). Limits are per-process
memory — correct for single-replica abuse mitigation; use Redis when
strict multi-replica counting is required (documented, not implemented).
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .logging import get_logger

log = get_logger(__name__)

_PREFIXES = ("/auth/", "/auth", "/public/", "/public")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool, per_minute: int):
        super().__init__(app)
        self.enabled = enabled
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, list[float]] = {}

    def _scoped(self, path: str) -> bool:
        return path == "/auth" or path.startswith(_PREFIXES)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._scoped(request.url.path):
            return await call_next(request)
        # Settings are re-read per request (not just constructor args) so
        # tests can toggle the limiter via monkeypatch without rebuilding app.
        # Import here: settings may be monkeypatched in tests before requests.
        from .config import settings

        enabled = bool(self.enabled or settings.rate_limit_enabled)
        if not enabled:
            return await call_next(request)
        limit = max(1, settings.rate_limit_per_minute or self.per_minute)
        window = 60.0
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{request.url.path.rsplit('/', 1)[0]}"
        hits = [t for t in self._hits.get(key, []) if now - t < window]
        if len(hits) >= limit:
            retry_after = int(window - (now - hits[0])) + 1
            log.warning("Rate limit hit", client=client, path=request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Slow down and retry."},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        self._hits[key] = hits
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response
