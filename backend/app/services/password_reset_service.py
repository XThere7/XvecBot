"""
services/password_reset_service.py
Single-use password reset tokens and their rate limiting.

Security model
--------------
  * Tokens are ``secrets.token_urlsafe(32)`` (256 bits). Only the SHA-256
    hash is stored; the raw token exists solely in the emailed link.
  * Consumption is a single conditional UPDATE ... RETURNING — exactly one
    concurrent request can win; everyone else gets the generic 400.
  * Requesting a new link marks the user's earlier unused tokens used, so an
    old link dies the moment a newer one is created.
  * Lookups always go through the hash; the raw token never touches SQL or
    logs.

Rate limiting (per-worker, in-process — see core/rate_limit.py for the
scaling note) protects POST /auth/forgot-password with two fixed one-hour
windows: per email address and per client IP. The 429 body is the same
neutral sentence as the 200 so the limiter leaks nothing about the account.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)

MIN_PASSWORD_LENGTH = 8  # Must match AuthRequest.password min_length.

# ── Rate limiting ────────────────────────────────────────────────────────────
_RATE_WINDOW_SECONDS = 3600.0
_rate_buckets: dict[str, list[float]] = {}


class PasswordResetRateLimited(Exception):
    """Raised when an hourly bucket is exhausted (the endpoint maps it to 429)."""


def reset_rate_limit_state() -> None:
    """Clear all buckets (unit tests)."""
    _rate_buckets.clear()


def _check_bucket(key: str, limit: int) -> None:
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    hits = [t for t in _rate_buckets.get(key, []) if t > cutoff]
    if len(hits) >= max(1, limit):
        raise PasswordResetRateLimited()
    hits.append(now)
    _rate_buckets[key] = hits


def check_email_rate_limit(email: str) -> None:
    """Hourly per-email bucket."""
    _check_bucket(f"email:{email.lower()}", settings.password_reset_max_per_email_per_hour)


def check_ip_rate_limit(ip: str) -> None:
    """Hourly per-IP bucket."""
    _check_bucket(f"ip:{ip}", settings.password_reset_max_per_ip_per_hour)


def check_rate_limits(email: str, ip: str) -> None:
    """Enforce both hourly buckets before any DB work happens."""
    check_email_rate_limit(email)
    check_ip_rate_limit(ip)


# Neutral, account-existence-proof response body for POST /auth/forgot-password.
FORGOT_RESPONSE = {
    "message": "If an account exists with this email address, you'll receive "
    "instructions to reset your password."
}

# Same copy on 429 so the limiter never confirms whether an account exists.
FORGOT_RATE_LIMITED = FORGOT_RESPONSE

# A simple structural check only; the endpoint treats malformed addresses the
# same as unknown ones and never sends mail for them.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_email(value: str) -> bool:
    return bool(_EMAIL_SHAPE.match((value or "").strip()))


# ── Tokens ───────────────────────────────────────────────────────────────────
def hash_token(raw: str) -> str:
    """SHA-256 of the raw token — the only representation ever stored."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


async def create_reset_token(
    db, user_id: str, ip: str, ttl_minutes: int | None = None
) -> str:
    """
    Invalidate the user's earlier unused links and insert a fresh token.

    Commits inside the caller's transaction scope (the caller owns commit) so
    the insert and the invalidation can never be observed separately.
    ``ttl_minutes`` overrides the default reset expiry (used by admin
    invites, which live longer).
    """
    raw = generate_token()
    now = datetime.now(timezone.utc)
    minutes = (
        settings.password_reset_token_ttl_minutes
        if ttl_minutes is None
        else int(ttl_minutes)
    )
    expires_at = now + timedelta(minutes=minutes)
    now_iso = now.isoformat()
    await db.execute(
        "UPDATE password_reset_tokens SET used_at = ? "
        "WHERE user_id = ? AND used_at IS NULL",
        (now_iso, user_id),
    )
    await db.execute(
        "INSERT INTO password_reset_tokens "
        "(id, user_id, token_hash, created_at, expires_at, used_at, requested_ip) "
        "VALUES (?, ?, ?, ?, ?, NULL, ?)",
        (str(uuid.uuid4()), user_id, hash_token(raw), now_iso, expires_at.isoformat(), ip),
    )
    return raw


async def consume_token(db, raw: str) -> str | None:
    """
    Atomically mark a token used and return its user_id.

    A single conditional UPDATE ... RETURNING means two simultaneous requests
    can never both succeed: the second sees ``used_at`` already set and gets
    no row. Returns None for unknown, used, expired, or otherwise bad tokens.
    """
    token_hash = hash_token(raw)
    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "UPDATE password_reset_tokens SET used_at = ? "
        "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ? "
        "RETURNING user_id",
        (now, token_hash, now),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    return row["user_id"]


async def is_token_valid(db, raw: str) -> bool:
    """Read-only check for the /validate endpoint. Never consumes the token."""
    token_hash = hash_token(raw)
    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "SELECT id FROM password_reset_tokens "
        "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
        (token_hash, now),
    )
    return await cur.fetchone() is not None
