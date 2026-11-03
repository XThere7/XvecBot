"""
Plan resolution and entitlement checks for XvecBot.

This module is the single source of truth for the requested Free / Standard /
Pro / 21-day-trial limits and TZS prices. Every entitlement check in the
platform should resolve the caller through :func:`resolve_effective_plan` and
then use :func:`get_limits` / :func:`check_limit`.

The trial is deliberately represented as an *effective* plan, not a stored
plan. `users.plan` stays `free` for a trial account; access is elevated only
while `trial_ends_at` is in the future. When the timestamp passes, no database
mutation is needed — the next request simply resolves to the base plan.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

PlanName = Literal["free", "standard", "pro", "trial"]

TRIAL_DAYS = 21
PLAN_IDS = ("free", "standard", "pro")
REFRESH_POLICIES = ("manual", "weekly", "daily")
_REFRESH_RANK = {"manual": 0, "weekly": 1, "daily": 2}
PLAN_RANK = {"free": 0, "standard": 1, "pro": 2, "trial": 2}

# None means unlimited.
PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "trial": {
        "agents": None,
        "documents": None,
        "pages_indexed": None,
        "website_sources": None,
        "website_refresh": "daily",
        "api_keys": None,
        "chat_messages": None,
        "embed_tokens": None,
    },
    "pro": {
        "agents": None,
        "documents": None,
        "pages_indexed": None,
        "website_sources": None,
        "website_refresh": "daily",
        "api_keys": None,
        "chat_messages": None,
        "embed_tokens": None,
    },
    "standard": {
        "agents": 5,
        "documents": 50,
        "pages_indexed": 500,
        "website_sources": 5,
        "website_refresh": "weekly",
        "api_keys": 3,
        "chat_messages": 5_000,
        "embed_tokens": 5,
    },
    "free": {
        "agents": 1,
        "documents": 5,
        "pages_indexed": 50,
        "website_sources": 1,
        "website_refresh": "manual",
        "api_keys": 0,
        "chat_messages": 100,
        "embed_tokens": 1,
    },
}

PLAN_PRICES_TZS: dict[str, int] = {
    "free": 0,
    "standard": 7_800,
    "pro": 15_800,
}

PLAN_NAMES: dict[str, str] = {
    "free": "Free",
    "standard": "Standard",
    "pro": "Pro",
    "trial": "Pro trial",
}


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse the ISO timestamps stored in TEXT columns, tolerating bad rows."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_plan_id(value: Any) -> PlanName:
    """Return a known base plan id, falling back to Free."""
    normalized = str(value or "").strip().lower()
    if normalized in ("free", "standard", "pro"):
        return normalized  # type: ignore[return-value]
    return "free"


def resolve_effective_plan(user: dict | None) -> PlanName:
    """
    Return the user's effective plan right now.

    An unexpired `trial_ends_at` wins and returns "trial". Otherwise the base
    `plan` column is used. This is the only function that decides whether a
    user is in the trial.
    """
    user = user or {}
    trial_end = _parse_datetime(user.get("trial_ends_at"))
    if trial_end is not None and datetime.now(timezone.utc) < trial_end:
        return "trial"
    return normalize_plan_id(user.get("plan"))


def get_limits(user: dict | None) -> dict[str, Any]:
    """Return a copy of the limits for the user's effective plan."""
    return dict(PLAN_LIMITS[resolve_effective_plan(user)])


def get_limits_for_plan(plan_id: str | None) -> dict[str, Any]:
    """Return limits by effective plan id (used after workspace resolution)."""
    normalized = str(plan_id or "").strip().lower()
    if normalized not in PLAN_LIMITS:
        normalized = "free"
    return dict(PLAN_LIMITS[normalized])


def check_limit(
    user: dict | None, feature: str, current_count: int
) -> tuple[bool, str]:
    """
    Check whether the user can add one more item of `feature`.

    Returns ``(allowed, reason)``; ``reason`` is empty when allowed. The
    caller is responsible for raising the HTTP error (the platform uses 403
    for plan limits and 429 for the monthly chat allowance).
    """
    limits = get_limits(user)
    limit = limits.get(feature)
    if limit is None:  # unlimited
        return True, ""
    if current_count >= int(limit):
        plan = resolve_effective_plan(user)
        return False, (
            f"Your {plan} plan allows a maximum of {limit} {feature}. "
            "Upgrade to Standard or Pro to add more."
        )
    return True, ""


def check_limit_for_plan(
    plan_id: str | None, feature: str, current_count: int
) -> tuple[bool, str]:
    """Same as :func:`check_limit`, but for an already-resolved plan."""
    limits = get_limits_for_plan(plan_id)
    limit = limits.get(feature)
    if limit is None:
        return True, ""
    if current_count >= int(limit):
        plan = str(plan_id or "free")
        return False, (
            f"Your {plan} plan allows a maximum of {limit} {feature}. "
            "Upgrade to Standard or Pro to add more."
        )
    return True, ""


def get_trial_status(user: dict | None) -> dict[str, Any]:
    """Trial metadata for GET /auth/me and the billing summary."""
    user = user or {}
    trial_ends_at = user.get("trial_ends_at")
    effective_plan = resolve_effective_plan(user)
    is_trial = effective_plan == "trial"
    days_remaining: int | None = None
    if is_trial:
        trial_end = _parse_datetime(trial_ends_at)
        if trial_end is not None:
            seconds = (trial_end - datetime.now(timezone.utc)).total_seconds()
            days_remaining = max(0, math.ceil(seconds / 86_400))
    return {
        "is_trial": is_trial,
        "trial_ends_at": trial_ends_at,
        "days_remaining": days_remaining,
        "effective_plan": effective_plan,
        "base_plan": normalize_plan_id(user.get("plan")),
    }


def trial_end_from(now: datetime | None = None) -> str:
    """ISO timestamp exactly 21 days from ``now`` (UTC)."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current + timedelta(days=TRIAL_DAYS)).isoformat()


def refresh_policy_allowed(user: dict | None, requested: str) -> bool:
    """True when the requested policy is within the user's plan."""
    allowed = get_limits(user)["website_refresh"]
    return _REFRESH_RANK.get(str(requested), -1) <= _REFRESH_RANK.get(
        str(allowed), 0
    )


def refresh_policy_for_plan(plan_id: str | None) -> str:
    return str(get_limits_for_plan(plan_id)["website_refresh"])


def refresh_policy_rank(policy: str | None) -> int:
    return _REFRESH_RANK.get(str(policy or "manual"), 0)
