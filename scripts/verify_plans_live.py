"""
Live verification for the user-level trial, plan catalogue and entitlement
gates. Run against a real PostgreSQL-backed API:

    docker run --rm --network host \
      -e E2E_API=http://127.0.0.1:8000 \
      -e E2E_DSN=postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase \
      -v "$PWD":/workspace -w /workspace \
      botbase-backend-social:local python scripts/verify_plans_live.py

It creates one disposable account, exercises the gates, then removes the
account and its workspace. Exits non-zero on the first failed check.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import asyncpg
import httpx

API = os.environ.get("E2E_API", "http://127.0.0.1:8000")
DSN = os.environ.get(
    "E2E_DSN",
    "postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase",
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(cond: bool, label: str, extra: object = "") -> None:
    if cond:
        PASSED.append(label)
        print(f"PASS  {label}", flush=True)
        return
    FAILED.append(f"{label} {extra}".strip())
    print(f"FAIL  {label} {extra}".strip(), flush=True)


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def main() -> None:
    tag = uuid.uuid4().hex[:10]
    email = f"plan-live-{tag}@example.com"
    password = "PlanVerify!2026"

    user_id = ""
    ws = ""

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        # ── public catalogue ───────────────────────────────────────────────
        r = await c.get("/plans")
        body = r.json()
        plans = {p["id"]: p for p in body["plans"]}
        check(r.status_code == 200, "GET /plans is public", r.text[:200])
        check(
            set(plans) == {"free", "standard", "pro"},
            "catalogue has Free, Standard and Pro",
            json.dumps(list(plans)),
        )
        check(
            plans["free"]["price_tzs"] == 0
            and plans["standard"]["price_tzs"] == 7800
            and plans["pro"]["price_tzs"] == 15800,
            "prices are 0 / 7,800 / 15,800 TZS",
        )
        f = plans["free"]["limits"]
        s = plans["standard"]["limits"]
        p = plans["pro"]["limits"]
        check(
            (f["agents"], f["documents"], f["pages_indexed"]) == (1, 5, 50)
            and f["website_sources"] == 1
            and f["website_refresh"] == "manual"
            and f["api_keys"] == 0
            and f["chat_messages"] == 100
            and f["embed_tokens"] == 1,
            "Free limits match the approved matrix",
            json.dumps(f),
        )
        check(
            (s["agents"], s["documents"], s["pages_indexed"]) == (5, 50, 500)
            and s["website_sources"] == 5
            and s["website_refresh"] == "weekly"
            and s["api_keys"] == 3
            and s["chat_messages"] == 5000
            and s["embed_tokens"] == 5,
            "Standard limits match the approved matrix",
            json.dumps(s),
        )
        check(
            all(
                p[k] is None
                for k in (
                    "agents",
                    "documents",
                    "pages_indexed",
                    "website_sources",
                    "api_keys",
                    "chat_messages",
                    "embed_tokens",
                )
            )
            and p["website_refresh"] == "daily",
            "Pro limits are unlimited with daily refresh",
            json.dumps(p),
        )
        check(body["trial"]["duration_days"] == 21, "trial is advertised as 21 days")
        check(
            body["payments_configured"] is False
            and body["upgrade_available"] is False,
            "payments are explicitly not configured",
        )

        # ── registration -> new trial ──────────────────────────────────────
        r = await c.post(
            "/auth/register", json={"email": email, "password": password}
        )
        check(r.status_code == 201, "registration succeeds", r.text[:200])
        token = r.json()["access_token"]
        user_id = r.json()["user_id"]
        headers = {"Authorization": f"Bearer {token}"}

        r = await c.get("/auth/me", headers=headers)
        me = r.json()
        check(
            me["plan"]["base"] == "free"
            and me["plan"]["effective"] == "trial"
            and me["plan"]["is_trial"] is True
            and me["plan"]["days_remaining"] in (20, 21),
            "new account starts on a 21-day Pro trial",
            json.dumps(me.get("plan")),
        )
        check(
            me["limits"]["agents"] is None
            and me["limits"]["chat_messages"] is None,
            "trial effective limits are Pro-equivalent",
        )

        r = await c.post(
            "/workspaces",
            json={"name": f"Plan verify {tag}"},
            headers=headers,
        )
        check(r.status_code in (200, 201), "workspace created", r.text[:200])
        ws = r.json()["id"]

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        billing = r.json()
        check(
            billing["plan"]["id"] == "pro"
            and billing["is_trial"] is True
            and billing["base_plan"] == "free",
            "trial workspace displays Pro with a Free base",
            r.text[:200],
        )
        check(
            billing["payments_configured"] is False
            and billing["upgrade_available"] is False,
            "billing exposes no payment flow",
        )

        # Trial is Pro-equivalent: two agents exceed the Free cap of one.
        agent_ids = []
        for index in range(2):
            r = await c.post(
                f"/workspaces/{ws}/agents",
                json={
                    "name": f"Agent {index}",
                    "system_prompt": "Answer from the knowledge base.",
                },
                headers=headers,
            )
            check(
                r.status_code == 201,
                f"trial permits agent {index + 1} (beyond Free cap)",
                r.text[:200],
            )
            agent_ids.append(r.json()["id"])

        # ── expire trial and verify Free gates ─────────────────────────────
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = $1",
                user_id,
            )
        finally:
            await conn.close()

        r = await c.get("/auth/me", headers=headers)
        me = r.json()
        check(
            me["plan"]["base"] == "free"
            and me["plan"]["effective"] == "free"
            and me["plan"]["is_trial"] is False
            and me["limits"]["agents"] == 1,
            "expired trial resolves to Free without changing users.plan",
            json.dumps(me.get("plan")),
        )
        check(me["plan"]["days_remaining"] is None, "expired trial has no days left")

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        billing = r.json()
        check(
            billing["plan"]["id"] == "free" and billing["is_trial"] is False,
            "billing follows the expired trial",
            r.text[:200],
        )
        check(
            billing["usage"]["agents"]["limit"] == 1
            and billing["usage"]["agents"]["used"] == 2
            and billing["usage"]["chat_messages"]["limit"] == 100,
            "billing reports the new Free limits and current usage",
            json.dumps(billing.get("usage")),
        )

        r = await c.post(
            f"/workspaces/{ws}/agents",
            json={"name": "Blocked agent", "system_prompt": "Nope."},
            headers=headers,
        )
        check(r.status_code == 403, "Free blocks a third agent", r.text[:200])
        detail = r.json().get("detail") or {}
        check(
            detail.get("resource") == "agents"
            and detail.get("used") == 2
            and detail.get("limit") == 1,
            "agent gate returns structured 403 details",
            r.text[:200],
        )

        r = await c.post(
            f"/workspaces/{ws}/api-keys",
            json={"name": "Blocked key"},
            headers=headers,
        )
        check(r.status_code == 403, "Free blocks developer API keys", r.text[:200])
        detail = r.json().get("detail") or {}
        check(
            detail.get("resource") == "api_keys" and detail.get("limit") == 0,
            "API-key gate returns structured 403 details",
            r.text[:200],
        )

        r = await c.get(f"/plans")
        check(r.status_code == 200, "public catalogue remains available")

        # ── embed-token cap on Free (1 per agent) ──────────────────────────
        r = await c.post(
            f"/workspaces/{ws}/agents/{agent_ids[0]}/tokens",
            json={"label": "first"},
            headers=headers,
        )
        check(r.status_code == 201, "Free permits its first embed token", r.text[:200])
        r = await c.post(
            f"/workspaces/{ws}/agents/{agent_ids[0]}/tokens",
            json={"label": "second"},
            headers=headers,
        )
        check(r.status_code == 403, "Free blocks a second embed token", r.text[:200])
        check(
            (r.json().get("detail") or {}).get("resource") == "embed_tokens",
            "embed-token gate returns the right resource",
            r.text[:200],
        )

        # ── monthly chat quota: prefill exactly 100 and prove a 429 ────────
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                """INSERT INTO usage_monthly (id, user_id, month, chat_messages)
                   VALUES ($1, $2, $3, 100)
                   ON CONFLICT (user_id, month)
                   DO UPDATE SET chat_messages = 100""",
                str(uuid.uuid4()),
                user_id,
                month_key(),
            )
        finally:
            await conn.close()

        r = await c.post(
            f"/workspaces/{ws}/agents/{agent_ids[0]}/chat",
            json={"message": "Will this be blocked?"},
            headers=headers,
        )
        check(r.status_code == 429, "exhausted monthly chat quota returns 429", r.text[:200])
        detail = r.json().get("detail") or {}
        check(
            detail.get("resource") == "chat_messages"
            and detail.get("used") == 100
            and detail.get("limit") == 100,
            "chat quota returns structured 429 details",
            r.text[:200],
        )
        r = await c.get(
            f"/workspaces/{ws}/agents/{agent_ids[0]}/conversations",
            headers=headers,
        )
        check(
            r.status_code == 200 and r.json() == [],
            "blocked chat did not create a conversation",
            r.text[:200],
        )

        # ── downgrade: a daily source is clamped to the Free manual policy ─
        source_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                """INSERT INTO website_sources
                   (id, workspace_id, url, name, status, pages_discovered,
                    pages_indexed, last_synced_at, next_sync_at, refresh_policy,
                    error_message, created_at, updated_at)
                   VALUES ($1, $2, 'https://example.com', 'Example',
                           'synced', 0, 0, NULL, $3, 'daily', NULL, $4, $4)""",
                source_id,
                ws,
                now,
                now,
            )
        finally:
            await conn.close()

        r = await c.post(
            f"/workspaces/{ws}/websites/{source_id}/refresh",
            headers=headers,
        )
        check(
            r.status_code == 202,
            "refresh clamps a daily source instead of running it",
            r.text[:200],
        )
        conn = await asyncpg.connect(DSN)
        try:
            row = await conn.fetchrow(
                "SELECT refresh_policy, next_sync_at FROM website_sources WHERE id = $1",
                source_id,
            )
        finally:
            await conn.close()
        check(
            row is not None
            and row["refresh_policy"] == "manual"
            and row["next_sync_at"] is None,
            "downgraded source is stored as manual with no schedule",
            dict(row) if row else None,
        )

        # ── paid plan changes remain unavailable without payments ──────────
        r = await c.post(
            f"/workspaces/{ws}/billing/plan",
            json={"plan": "pro"},
            headers=headers,
        )
        check(r.status_code == 503, "paid plan change is refused (503)", r.text[:200])
        check(
            (r.json().get("detail") or {}).get("code")
            == "payments_not_configured",
            "paid plan change says payments are not configured",
            r.text[:200],
        )

        # ── cleanup ────────────────────────────────────────────────────────
        r = await c.delete(f"/workspaces/{ws}", headers=headers)
        check(r.status_code in (200, 204), "test workspace deleted", r.text[:200])

    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("DELETE FROM usage_monthly WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)
    finally:
        await conn.close()

    print(
        f"\n=== LIVE PLAN VERIFY: {len(PASSED)} passed, {len(FAILED)} failed ==="
    )
    if FAILED:
        for item in FAILED:
            print("  FAILED:", item)
        sys.exit(1)
    print("LIVE_PLAN_VERIFY_RESULT=PASS")


if __name__ == "__main__":
    asyncio.run(main())
