"""
core/middleware.py
ASGI middleware for the unauthenticated public surface (/public/*).

Why this exists
---------------
The app-wide CORSMiddleware in main.py is deliberately restrictive: it only
allows the dashboard's own dev origins, because the JWT endpoints should never
be callable from arbitrary sites. That restriction would also block the embedded
widget, which by definition runs on someone else's domain (a customer pasting a
<script> tag into their own site). A preflight from an unlisted origin is
rejected with 400 by Starlette's CORSMiddleware before it ever reaches a route,
so no amount of per-token origin checking downstream can rescue it.

This middleware therefore grants CORS for /public/* only, and leaves every other
route to the restrictive global policy. Real access control for the widget lives
one layer down, in embed_service._check_origin(), which enforces the token's
per-widget allowed_origins list.

Ordering
--------
Registered in main.py *after* CORSMiddleware, which makes it the outermost
middleware (Starlette's add_middleware inserts at index 0, so the last one
added wraps everything). That matters: the outer layer must answer the preflight
itself, otherwise the inner CORSMiddleware 400s the request first.

Credentials
-----------
No Access-Control-Allow-Credentials is sent for /public/*. The widget
authenticates with the embed token in the JSON body, never with a cookie, so
credentialed CORS would grant more than the design needs. Reflecting arbitrary
origins *and* allowing credentials would let any site make the browser attach
cookies to this surface.
"""
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PREFIX = "/public"

# Mirrors the browser cache window used by the global CORSMiddleware.
PREFLIGHT_MAX_AGE = 600
ALLOWED_METHODS = "GET, POST, OPTIONS"


def is_public_path(path: str) -> bool:
    """True for /public and /public/... but not /publicity."""
    return path == PUBLIC_PREFIX or path.startswith(PUBLIC_PREFIX + "/")


def _add_vary_origin(headers: MutableHeaders) -> None:
    """Append Vary: Origin without clobbering a Vary set further down the stack."""
    existing = headers.get("vary", "")
    values = [v.strip() for v in existing.split(",") if v.strip()]
    if "origin" not in [v.lower() for v in values]:
        values.append("Origin")
    headers["vary"] = ", ".join(values)


class PublicSurfaceMiddleware:
    """Open CORS + hardening headers for /public/* only."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_public_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)

        # Preflight: answer here so the restrictive inner CORSMiddleware never
        # sees (and rejects) the request.
        if request_headers.get("access-control-request-method"):
            response = PlainTextResponse("OK", status_code=200)
            self._apply_cors(response.headers, request_headers)
            self._apply_security_headers(response.headers)
            await response(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                self._apply_cors(headers, request_headers)
                self._apply_security_headers(headers)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    # ── header helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _apply_cors(headers: MutableHeaders, request_headers: Headers) -> None:
        origin = request_headers.get("origin")
        if not origin:
            return
        # Echo the caller's origin: any website may embed a widget, and the
        # per-token allow-list is enforced inside embed_service, not here.
        headers["access-control-allow-origin"] = origin
        headers["access-control-expose-headers"] = "content-type"
        _add_vary_origin(headers)

        # The app-wide CORSMiddleware sets Access-Control-Allow-Credentials on
        # every response (it runs with allow_credentials=True for the dashboard).
        # Reflected together with an open origin that would tell browsers to
        # attach cookies to this unauthenticated surface. The widget never uses
        # cookies — the token travels in the JSON body — so drop the header.
        if "access-control-allow-credentials" in headers:
            del headers["access-control-allow-credentials"]

        # A preflight must state the allowed method and headers, otherwise the
        # browser fails the check even though the status is 200. The widget
        # sends application/json, which is not a CORS-safelisted content type,
        # so the Allow-Headers echo is required in practice.
        if request_headers.get("access-control-request-method"):
            headers["access-control-allow-methods"] = ALLOWED_METHODS
            requested_headers = request_headers.get("access-control-request-headers")
            headers["access-control-allow-headers"] = requested_headers or "content-type"
            headers["access-control-max-age"] = str(PREFLIGHT_MAX_AGE)

    @staticmethod
    def _apply_security_headers(headers: MutableHeaders) -> None:
        # Applied to every /public response, including errors. Not applied to
        # the JWT-protected dashboard routes.
        headers["x-content-type-options"] = "nosniff"
        headers["x-frame-options"] = "SAMEORIGIN"
        headers["referrer-policy"] = "strict-origin-when-cross-origin"
