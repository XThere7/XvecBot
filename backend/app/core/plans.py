"""
core/plans.py
The BotBase subscription catalogue — the public shape of the plan tiers.

The canonical entitlement numbers live in :mod:`app.core.plan`. This module
wraps them in the marketing/API object used by the pricing page and billing
summary. Existing workspace-level usage (storage, members, social imports) is
retained as extra limits while the new trial/pricing contract is the source of
truth for agents, documents, pages, websites, API keys, chat messages and
embed tokens.

Money is stored as whole Tanzanian shillings (TZS). There is no payment
provider wired up yet: every new workspace starts on Free, and paid plans are
shown in the product but cannot be purchased.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .plan import (
    PLAN_IDS as _CORE_PLAN_IDS,
    PLAN_LIMITS,
    PLAN_PRICES_TZS,
    get_limits_for_plan,
)

MB = 1024 * 1024
GB = 1024 * MB

PLAN_IDS = _CORE_PLAN_IDS

LAUNCH_NOTE = (
    "Every new account includes a 21-day Pro trial. After the trial, the "
    "account moves to Free automatically. Paid plans are displayed for "
    "transparency and will become available once payments go live."
)

# Existing workspace-level entitlements that are not part of the new public
# trial/pricing contract but are still enforced by the product.
_LEGACY_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "storage_bytes": 100 * MB,
        "members": 1,
        "social_media_sources": 3,
    },
    "standard": {
        "storage_bytes": 1 * GB,
        "members": 3,
        "social_media_sources": 25,
    },
    "pro": {
        "storage_bytes": 5 * GB,
        "members": 10,
        "social_media_sources": 100,
    },
}


@dataclass(frozen=True)
class Plan:
    """One subscription tier."""

    id: str
    name: str
    tagline: str
    price_tzs: int
    period: str  # "forever" | "month"
    recommended: bool
    limits: dict[str, Any]
    features: dict[str, Any] = field(default_factory=dict)
    # Feature keys that are advertised but not implemented yet. The UI renders
    # a "Soon" badge instead of pretending the capability is live.
    coming_soon: tuple[str, ...] = ()

    @property
    def price_label(self) -> str:
        return "Free" if self.price_tzs == 0 else f"TZS {self.price_tzs:,}"

    @property
    def price_display(self) -> str:
        if self.price_tzs == 0:
            return "Free forever"
        return f"TZS {self.price_tzs:,} / month"

    # ── Backwards-compatible property access used by older services ──────────
    @property
    def max_agents(self) -> int | None:
        return self.limits.get("agents")

    @property
    def monthly_responses(self) -> int | None:
        return self.limits.get("chat_messages")

    @property
    def storage_bytes(self) -> int:
        return int(self.limits.get("storage_bytes") or 0)

    @property
    def max_members(self) -> int:
        return int(self.limits.get("members") or 1)

    @property
    def max_social_media_sources(self) -> int:
        return int(self.limits.get("social_media_sources") or 0)

    def as_dict(self) -> dict[str, Any]:
        """JSON shape returned by GET /plans and GET /billing/plans."""
        return {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "price_tzs": self.price_tzs,
            "price_label": self.price_label,
            "price_display": self.price_display,
            "period": self.period,
            "recommended": self.recommended,
            "limits": dict(self.limits),
            "features": dict(self.features),
            "coming_soon": list(self.coming_soon),
        }


_FREE_FEATURES: dict[str, Any] = {
    "website_widget": True,
    "citations": True,
    "conversation_history": True,
    "lead_forms": False,
    "email_integration": False,
    "lead_qualification": False,
    "actions": False,
    "analytics": "usage",
    "whatsapp": False,
    "developer_api": False,
    "automations": False,
    "custom_branding": False,
    "support": "community",
}

_STANDARD_FEATURES: dict[str, Any] = {
    **_FREE_FEATURES,
    "email_integration": True,
    "lead_qualification": True,
    "actions": True,
    "analytics": "basic",
    "developer_api": True,
    "support": "standard",
}

_PRO_FEATURES: dict[str, Any] = {
    **_STANDARD_FEATURES,
    "whatsapp": True,
    "developer_api": True,
    "automations": True,
    "analytics": "advanced",
    "custom_branding": True,
    "support": "priority",
}


def _limits(plan_id: str) -> dict[str, Any]:
    limits = get_limits_for_plan(plan_id)
    limits.update(_LEGACY_LIMITS[plan_id])
    return limits


PLAN_CATALOG: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        tagline="Start free with the essentials, forever",
        price_tzs=PLAN_PRICES_TZS["free"],
        period="forever",
        recommended=False,
        limits=_limits("free"),
        features=dict(_FREE_FEATURES),
        coming_soon=(),
    ),
    "standard": Plan(
        id="standard",
        name="Standard",
        tagline="For small businesses ready to use AI every day",
        price_tzs=PLAN_PRICES_TZS["standard"],
        period="month",
        recommended=True,
        limits=_limits("standard"),
        features=dict(_STANDARD_FEATURES),
        coming_soon=("members",),
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        tagline="Unlimited scale for growing businesses and teams",
        price_tzs=PLAN_PRICES_TZS["pro"],
        period="month",
        recommended=False,
        limits=_limits("pro"),
        features=dict(_PRO_FEATURES),
        coming_soon=(
            "members",
            "whatsapp",
            "automations",
            "advanced_analytics",
            "custom_branding",
        ),
    ),
}


def get_plan(plan_id: str | None) -> Plan:
    """Resolve a plan id, falling back to Free for unknown/NULL values.

    The trial is an effective access state, not a purchasable tier; trial
    access maps to the Pro catalogue entry because its limits are identical.
    """
    normalized = (plan_id or "").strip().lower()
    if normalized == "trial":
        return PLAN_CATALOG["pro"]
    return PLAN_CATALOG.get(normalized, PLAN_CATALOG["free"])


def get_plan_limits(plan_id: str | None) -> dict[str, Any]:
    """Canonical requested limits (without legacy workspace extras)."""
    return get_limits_for_plan(plan_id)


def plan_list() -> list[Plan]:
    return [PLAN_CATALOG[plan_id] for plan_id in PLAN_IDS]
