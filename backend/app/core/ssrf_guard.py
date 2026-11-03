"""
SSRF protection for user-supplied URLs.

Every URL that arrives from a workspace owner must pass ``validate_url``
before it is fetched. Redirect destinations are re-validated as well, because
a public host can redirect to a private address.

The guard resolves DNS (with a short cache), rejects non-global addresses,
and never includes the resolved IP in an error message returned to the client.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from time import monotonic
from urllib.parse import urlparse

from fastapi import HTTPException

ALLOWED_SCHEMES = {"http", "https"}

# Explicit private / loopback / link-local / metadata ranges. ``is_global``
# below already covers these, but keeping the list makes the policy auditable
# and catches runtimes whose ``is_global`` behaviour differs.
BLOCKED_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),    # carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),     # documentation
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),    # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # documentation
    ipaddress.ip_network("203.0.113.0/24"),   # documentation
    ipaddress.ip_network("224.0.0.0/4"),      # multicast
    ipaddress.ip_network("240.0.0.0/4"),      # reserved
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),    # IPv4-mapped IPv6
]

# Hostnames that are never allowed regardless of what DNS returns.
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.internal",
    "169.254.169.254",
    "100.100.100.200",  # Alibaba Cloud metadata
}

_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
    ".corp",
)

_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]")
_DNS_CACHE: dict[str, tuple[float, tuple[str, ...]]] = {}
_DNS_CACHE_TTL_SECONDS = 300.0


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True unless the address is a public, globally routable IP."""
    try:
        address = ipaddress.ip_address(ip_str.split("%", 1)[0])
    except ValueError:
        return True  # unparseable — fail closed

    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped

    if not address.is_global:
        return True
    return any(address in network for network in BLOCKED_RANGES)


def _resolve(host: str) -> tuple[str, ...]:
    """Resolve a hostname, caching the answer briefly to avoid 50 DNS hits."""
    now = monotonic()
    cached = _DNS_CACHE.get(host)
    if cached is not None and now - cached[0] < _DNS_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(
            400, "Could not resolve the domain name. Please check the URL."
        ) from exc
    except OSError as exc:
        raise HTTPException(
            400, "Could not resolve the domain name. Please check the URL."
        ) from exc

    addresses = tuple(dict.fromkeys(info[4][0] for info in infos if info[4]))
    if not addresses:
        raise HTTPException(
            400, "Could not resolve the domain name. Please check the URL."
        )
    _DNS_CACHE[host] = (now, addresses)
    return addresses


def validate_url(url: str, *, resolve_dns: bool = True) -> str:
    """
    Validate a user-supplied URL against SSRF risks.

    Returns the stripped URL on success. Raises ``HTTPException(400)`` with a
    safe message on any violation. Internal IPs/hostnames are never echoed.
    """
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(400, "Invalid URL format.")
    candidate = url.strip()
    if len(candidate) > 2048:
        raise HTTPException(400, "URL is too long (maximum 2048 characters).")
    if "\\" in candidate or any(_CONTROL_CHARS.match(ch) for ch in candidate):
        raise HTTPException(400, "Invalid URL format.")

    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid URL format.")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HTTPException(400, "Only http:// and https:// URLs are supported.")
    if parsed.username or parsed.password:
        raise HTTPException(400, "URLs containing credentials are not allowed.")
    if port is not None and not (1 <= port <= 65535):
        raise HTTPException(400, "Invalid URL port.")

    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise HTTPException(400, "URL must include a valid hostname.")
    if "%" in host or any(_CONTROL_CHARS.match(ch) for ch in host):
        raise HTTPException(400, "Invalid URL format.")
    if host in BLOCKED_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise HTTPException(400, "This URL is not allowed.")

    # IP literal: validate directly, even when DNS resolution is disabled.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_ip(str(literal)):
            raise HTTPException(
                400, "This URL resolves to a restricted address and cannot be crawled."
            )
        return candidate

    # A single-label host is a LAN name in practice, never a public website.
    if "." not in host:
        raise HTTPException(400, "This URL is not allowed.")

    if resolve_dns:
        for address in _resolve(host):
            if _is_blocked_ip(address):
                raise HTTPException(
                    400,
                    "This URL resolves to a restricted address and cannot be crawled.",
                )

    return candidate


async def validate_url_async(url: str, *, resolve_dns: bool = True) -> str:
    """Async wrapper so API handlers never block the event loop on DNS."""
    return await asyncio.to_thread(validate_url, url, resolve_dns=resolve_dns)


async def safe_follow_redirect(response_url: str) -> None:
    """Re-validate a redirect destination before following it."""
    await validate_url_async(response_url, resolve_dns=True)
