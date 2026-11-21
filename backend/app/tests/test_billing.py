"""
tests/test_billing.py
Trial, plan catalogue, quotas and usage metering.

The rest of the suite runs with a Pro workspace (see conftest) so unrelated
tests are not constrained. These tests explicitly expire the registration
trial when they need the real Free state, then verify the 403/429 contract the
dashboard turns into an upgrade prompt.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from ..core import plan as plan_core
from ..core import plans
from ..core.database import get_db
from ..main import app
from ..services import agent_chat_service, plan_service


async def _register(client) -> dict:
    r = await client.post(
        "/auth/register",
        json={"email": f"bill-{uuid.uuid4().hex[:10]}@example.com", "password": "pw123456"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _me(client, headers: dict) -> dict:
    r = await client.get("/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _expire_trial(client, headers: dict) -> str:
    """Force the account onto its base Free plan for free-limit tests."""
    me = await _me(client, headers)
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (me["id"],),
        )
        await db.commit()
    return me["id"]


async def _workspace(
    client, headers, plan: str = "free", *, expire_trial: bool = True
) -> str:
    if expire_trial:
        await _expire_trial(client, headers)
    r = await client.post(
        "/workspaces", json={"name": f"Billing {uuid.uuid4().hex[:6]}"}, headers=headers
    )
    assert r.status_code == 201, r.text
    ws_id = r.json()["id"]
    await _set_plan(ws_id, plan)
    return ws_id


async def _set_plan(ws_id: str, plan: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE workspaces SET plan = ?, plan_started_at = '2026-10-01T00:00:00+00:00' "
            "WHERE id = ?",
            (plan, ws_id),
        )
        await db.commit()


async def _agent(client, headers, ws_id: str) -> dict:
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": "Support agent", "system_prompt": "Answer from the documents."},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_plan_catalogue_is_public_and_matches_strategy():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/plans")
        assert r.status_code == 200, r.text
        body = r.json()
        legacy = await client.get("/billing/plans")
        assert legacy.status_code == 200, legacy.text

    assert body["payments_configured"] is False
    assert body["upgrade_available"] is False
    assert body["trial"]["duration_days"] == 21
    plans_by_id = {p["id"]: p for p in body["plans"]}
    assert set(plans_by_id) == {"free", "standard", "pro"}
    assert {p["id"]: p for p in legacy.json()["plans"]} == plans_by_id

    free, standard, pro = (
        plans_by_id["free"],
        plans_by_id["standard"],
        plans_by_id["pro"],
    )
    assert (free["price_tzs"], free["period"]) == (0, "forever")
    assert (standard["price_tzs"], standard["period"]) == (7_800, "month")
    assert (pro["price_tzs"], pro["period"]) == (15_800, "month")
    assert standard["recommended"] is True

    assert free["limits"]["agents"] == 1
    assert free["limits"]["documents"] == 5
    assert free["limits"]["pages_indexed"] == 50
    assert free["limits"]["website_sources"] == 1
    assert free["limits"]["website_refresh"] == "manual"
    assert free["limits"]["api_keys"] == 0
    assert free["limits"]["chat_messages"] == 100
    assert free["limits"]["embed_tokens"] == 1

    assert standard["limits"]["agents"] == 5
    assert standard["limits"]["documents"] == 50
    assert standard["limits"]["pages_indexed"] == 500
    assert standard["limits"]["website_sources"] == 5
    assert standard["limits"]["website_refresh"] == "weekly"
    assert standard["limits"]["api_keys"] == 3
    assert standard["limits"]["chat_messages"] == 5_000
    assert standard["limits"]["embed_tokens"] == 5

    for key in (
        "agents",
        "documents",
        "pages_indexed",
        "website_sources",
        "api_keys",
        "chat_messages",
        "embed_tokens",
    ):
        assert pro["limits"][key] is None, key
    assert pro["limits"]["website_refresh"] == "daily"

    assert free["features"]["developer_api"] is False
    assert standard["features"]["developer_api"] is True
    assert pro["features"]["developer_api"] is True
    # Lead capture/data collection/custom forms are Standard+ and are now
    # shipped, so they must not be advertised as "coming soon".
    assert free["features"]["lead_forms"] is False
    assert free["features"]["actions"] is False
    assert standard["features"]["actions"] is True
    assert "lead_forms" not in free["coming_soon"]
    assert "actions" not in standard["coming_soon"]
    assert "whatsapp" in pro["coming_soon"]


@pytest.mark.asyncio
async def test_registration_starts_21_day_trial_and_expiry_drops_to_free():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        me = await _me(client, headers)
        assert me["plan"]["base"] == "free"
        assert me["plan"]["effective"] == "trial"
        assert me["plan"]["is_trial"] is True
        assert me["plan"]["days_remaining"] in (20, 21)
        assert me["limits"]["agents"] is None
        assert me["limits"]["chat_messages"] is None

        # Trial access is Pro-equivalent, so two agents are allowed even
        # though the stored plan is Free.
        r = await client.post(
            "/workspaces", json={"name": "Trial workspace"}, headers=headers
        )
        assert r.status_code == 201, r.text
        ws_id = r.json()["id"]
        await _agent(client, headers, ws_id)
        await _agent(client, headers, ws_id)

        await _expire_trial(client, headers)
        me = await _me(client, headers)
        assert me["plan"]["base"] == "free"
        assert me["plan"]["effective"] == "free"
        assert me["plan"]["is_trial"] is False
        assert me["plan"]["days_remaining"] is None
        assert me["limits"]["agents"] == 1
        assert me["limits"]["chat_messages"] == 100


@pytest.mark.asyncio
async def test_billing_summary_for_free_workspace():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)
        await _agent(client, headers, ws_id)

        r = await client.get(f"/workspaces/{ws_id}/billing", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["plan"]["id"] == "free"
    assert body["is_trial"] is False
    assert body["payments_configured"] is False
    assert body["usage"]["agents"] == {
        "used": 1,
        "limit": 1,
        "percent": 100.0,
        "unlimited": False,
    }
    assert body["usage"]["chat_messages"]["used"] == 0
    assert body["usage"]["chat_messages"]["limit"] == 100
    assert body["usage"]["chat_messages"]["resets_at"]
    assert body["usage"]["storage"]["used_bytes"] == 0
    assert body["usage"]["storage"]["limit_bytes"] == 100 * 1024 * 1024
    assert body["usage"]["members"]["enforced"] is False
    assert body["period"]["resets_at"].endswith("+00:00")
    assert body["period"]["resets_at"] == body["usage"]["chat_messages"]["resets_at"]


@pytest.mark.asyncio
async def test_free_plan_blocks_a_second_agent_with_upgrade_details():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)
        await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents",
            json={"name": "Second agent", "system_prompt": "Be helpful."},
            headers=headers,
        )
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "plan_limit_reached"
        assert detail["resource"] == "agents"
        assert detail["used"] == 1 and detail["limit"] == 1
        assert detail["plan"] == "free"
        assert detail["upgrade_required"] is True
        assert detail["payments_configured"] is False
        # Agents do not reset monthly.
        assert detail["resets_at"] is None


@pytest.mark.asyncio
async def test_free_document_limit_is_enforced(monkeypatch):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

    async with get_db() as db:
        for index in range(5):
            await db.execute(
                """INSERT INTO workspace_documents
                   (id, workspace_id, filename, file_path, file_type, size_bytes,
                    status, chunk_count, created_at)
                   VALUES (?, ?, ?, ?, 'txt', 1, 'ready', 0, ?)""",
                (
                    str(uuid.uuid4()),
                    ws_id,
                    f"doc-{index}.txt",
                    f"/tmp/doc-{index}.txt",
                    "2026-10-01T00:00:00+00:00",
                ),
            )
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("sixth.txt", b"hello", "text/plain")},
            headers=headers,
        )
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["resource"] == "documents"
        assert detail["used"] == 5 and detail["limit"] == 5
        assert detail["plan"] == "free"


@pytest.mark.asyncio
async def test_free_chat_quota_returns_429_before_the_conversation_starts(
    monkeypatch,
):
    # One-message Free allowance, already consumed, so the next chat turn is
    # rejected before conversation or LLM work.
    monkeypatch.setitem(plan_core.PLAN_LIMITS["free"], "chat_messages", 1)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)
        user_id = (await _me(client, headers))["id"]

        async with get_db() as db:
            await db.execute(
                """INSERT INTO usage_monthly
                   (id, user_id, month, chat_messages)
                   VALUES (?, ?, ?, 1)""",
                (
                    str(uuid.uuid4()),
                    user_id,
                    plan_service._utc_now().strftime("%Y-%m"),
                ),
            )
            await db.commit()

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/chat",
            json={"message": "What is your refund policy?"},
            headers=headers,
        )
        assert r.status_code == 429, r.text
        detail = r.json()["detail"]
        assert detail["resource"] == "chat_messages"
        assert detail["used"] == 1 and detail["limit"] == 1
        assert detail["plan"] == "free"
        assert detail["upgrade_required"] is True

        # The quota check happens before any conversation/user message is
        # written, so the customer can resume cleanly after upgrading.
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/conversations",
            headers=headers,
        )
        assert r.json() == []


@pytest.mark.asyncio
async def test_failed_generation_counts_as_chat_message_not_ai_response(monkeypatch):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)

        async def _no_context(*_args, **_kwargs):
            return [], []

        class _BrokenGenerator:
            last_model_used = ""

            async def generate(self, **_kwargs):
                raise RuntimeError("upstream model unavailable")

        monkeypatch.setattr(
            agent_chat_service, "_retrieve_knowledge", _no_context
        )
        monkeypatch.setattr(
            agent_chat_service, "build_generator", lambda: _BrokenGenerator()
        )

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/chat",
            json={"message": "Will this be charged?"},
            headers=headers,
        )
        assert r.status_code == 500, r.text

        billing = (
            await client.get(f"/workspaces/{ws_id}/billing", headers=headers)
        ).json()
        # Chat messages are metered before generation (the product contract),
        # while the AI-response analytics ledger only counts successes.
        assert billing["usage"]["chat_messages"]["used"] == 1
        async with get_db() as db:
            assert await plan_service.responses_used(db, ws_id) == 0


@pytest.mark.asyncio
async def test_storage_limit_blocks_upload_and_leaves_no_document(monkeypatch):
    # 10 bytes is smaller than the fixture file below. The legacy storage
    # entitlement lives in Plan.limits, so patch that rather than a property.
    monkeypatch.setitem(
        plans.PLAN_CATALOG["free"].limits, "storage_bytes", 10
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("policy.txt", b"x" * 200, "text/plain")},
            headers=headers,
        )
        assert r.status_code == 402, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "plan_limit_reached"
        assert detail["resource"] == "storage"
        assert detail["limit"] == 10
        assert detail["used"] == 0

        docs = (
            await client.get(f"/workspaces/{ws_id}/documents", headers=headers)
        ).json()
        assert docs == []


@pytest.mark.asyncio
async def test_storage_usage_tracks_upload_and_delete():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

        payload = b"refund policy: 14 days\n" * 40
        r = await client.post(
            f"/workspaces/{ws_id}/documents",
            files={"file": ("policy.txt", payload, "text/plain")},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]
        assert r.json()["size_bytes"] == len(payload)

        billing = (
            await client.get(f"/workspaces/{ws_id}/billing", headers=headers)
        ).json()
        assert billing["usage"]["storage"]["used_bytes"] == len(payload)
        assert billing["usage"]["storage"]["limit_bytes"] == 100 * 1024 * 1024

        r = await client.delete(
            f"/workspaces/{ws_id}/documents/{doc_id}", headers=headers
        )
        assert r.status_code == 204, r.text
        billing = (
            await client.get(f"/workspaces/{ws_id}/billing", headers=headers)
        ).json()
        assert billing["usage"]["storage"]["used_bytes"] == 0


@pytest.mark.asyncio
async def test_developer_api_is_locked_on_free_and_allowed_on_standard():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

        r = await client.post(
            f"/workspaces/{ws_id}/api-keys", json={"name": "blocked"}, headers=headers
        )
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["resource"] == "api_keys"
        assert detail["plan"] == "free"
        assert detail["limit"] == 0

        await _set_plan(ws_id, "standard")
        for index in range(3):
            r = await client.post(
                f"/workspaces/{ws_id}/api-keys",
                json={"name": f"allowed-{index}"},
                headers=headers,
            )
            assert r.status_code == 201, r.text
        r = await client.post(
            f"/workspaces/{ws_id}/api-keys", json={"name": "fourth"}, headers=headers
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["resource"] == "api_keys"


@pytest.mark.asyncio
async def test_free_embed_token_limit_is_one_per_agent():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)
        agent = await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/tokens",
            json={"label": "First"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/tokens",
            json={"label": "Second"},
            headers=headers,
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["resource"] == "embed_tokens"


@pytest.mark.asyncio
async def test_paid_plan_changes_are_refused_until_payments_exist():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

        r = await client.post(
            f"/workspaces/{ws_id}/billing/plan",
            json={"plan": "pro"},
            headers=headers,
        )
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["code"] == "payments_not_configured"

        # Requesting the current workspace plan is a harmless no-op.
        r = await client.post(
            f"/workspaces/{ws_id}/billing/plan",
            json={"plan": "free"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["plan"]["id"] == "free"

        r = await client.post(
            f"/workspaces/{ws_id}/billing/plan",
            json={"plan": "enterprise"},
            headers=headers,
        )
        assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_usage_period_is_calendar_month_utc():
    start, end = plan_service.period_bounds()
    assert start.endswith("-01T00:00:00+00:00")
    assert end.endswith("-01T00:00:00+00:00")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

    async with get_db() as db:
        await plan_service.record_ai_response(db, ws_id)
        assert await plan_service.responses_used(db, ws_id, start, end) == 1
        assert await plan_service.responses_used(db, ws_id, end, end) == 0


@pytest.mark.asyncio
async def test_operator_can_set_plan_and_unknown_plan_is_rejected():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers)

    async with get_db() as db:
        updated = await plan_service.set_workspace_plan(db, ws_id, "standard")
        assert updated["plan"] == "standard"
        with pytest.raises(ValueError):
            await plan_service.set_workspace_plan(db, ws_id, "enterprise")
