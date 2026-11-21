"""
tests/test_engagement.py
Agent Actions, lead generation, data collection, custom forms, support
escalation and the Email Agent.

The chat/email tests patch the LLM and retrieval boundary, but everything below
that boundary — database writes, validation, plan gates, tenant scoping,
deduplication, approvals and simulated delivery — runs against the real SQLite
schema created by ``init_db``.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from ..core.database import get_db
from ..main import app
from ..services import agent_chat_service


class _FakeGenerator:
    last_model_used = "fake/model"

    def __init__(self, answer: str):
        self.answer = answer

    async def generate(self, **_kwargs):
        return self.answer


async def _register(client) -> dict:
    r = await client.post(
        "/auth/register",
        json={
            "email": f"eng-{uuid.uuid4().hex[:10]}@example.com",
            "password": "pw123456",
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _expire_trial(headers: dict) -> None:
    me = (await _client_get("/auth/me", headers)).json()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (me["id"],),
        )
        await db.commit()


async def _client_get(path: str, headers: dict):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers)


async def _workspace(client, headers: dict, plan: str = "pro") -> str:
    if plan == "free":
        await _expire_trial(headers)
    r = await client.post(
        "/workspaces",
        json={"name": f"Eng {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    ws_id = r.json()["id"]
    async with get_db() as db:
        await db.execute("UPDATE workspaces SET plan = ? WHERE id = ?", (plan, ws_id))
        await db.commit()
    return ws_id


async def _agent(client, headers: dict, ws_id: str, **extra) -> dict:
    r = await client.post(
        f"/workspaces/{ws_id}/agents",
        json={
            "name": "Sales assistant",
            "system_prompt": "Answer from the knowledge base.",
            **extra,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _action(client, headers, ws_id, agent_id, action_type) -> dict:
    r = await client.get(
        f"/workspaces/{ws_id}/agents/{agent_id}/actions", headers=headers
    )
    assert r.status_code == 200, r.text
    return next(
        item for item in r.json()["catalog"] if item["action_type"] == action_type
    )


@pytest.mark.asyncio
async def test_free_plan_blocks_standard_actions():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "free")
        agent = await _agent(client, headers, ws_id)

        catalog = await _action(client, headers, ws_id, agent["id"], "lead_capture")
        assert catalog["plan_available"] is False
        assert catalog["locked_reason"]

        r = await client.put(
            f"/workspaces/{ws_id}/agents/{agent['id']}/actions/lead_capture",
            json={"is_active": True},
            headers=headers,
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "plan_feature_locked"

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/collections",
            json={
                "name": "Free collection",
                "fields": [
                    {"key": "email", "label": "Email", "type": "email", "required": True}
                ],
            },
            headers=headers,
        )
        assert r.status_code == 403, r.text

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/forms",
            json={
                "title": "Free form",
                "fields": [
                    {"key": "email", "label": "Email", "type": "email", "required": True}
                ],
            },
            headers=headers,
        )
        assert r.status_code == 403, r.text

        # Support escalation is available on every plan.
        support = await _action(
            client, headers, ws_id, agent["id"], "knowledge_support"
        )
        assert support["plan_available"] is True


@pytest.mark.asyncio
async def test_lead_capture_deduplicates_and_is_tenant_scoped():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers_a = await _register(client)
        headers_b = await _register(client)
        ws_a = await _workspace(client, headers_a, "standard")
        ws_b = await _workspace(client, headers_b, "standard")
        agent_a = await _agent(client, headers_a, ws_a)
        agent_b = await _agent(client, headers_b, ws_b)

        entry = await _action(client, headers_a, ws_a, agent_a["id"], "lead_capture")
        assert entry["plan_available"] is True
        action = entry["action"]
        assert action is not None
        assert action["config"]["require_consent"] is True

        form = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/actions/{action['id']}/form",
            headers=headers_a,
        )
        assert form.status_code == 200, form.text
        assert any(f["key"] == "email" for f in form.json()["fields"])

        data = {
            "full_name": "Ada Mushi",
            "email": "ada@example.com",
            "phone": "+255 712 345 678",
            "company": "Ada Traders",
            "interest": "Wholesale pricing",
            "budget": "TZS 500,000",
            "notes": "Call after 4pm",
            "_consent": True,
        }
        r = await client.post(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/actions/{action['id']}/submit",
            json={"data": data},
            headers=headers_a,
        )
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "lead"

        # Same email again merges into the same lead (no duplicate).
        r = await client.post(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/actions/{action['id']}/submit",
            json={"data": {**data, "interest": "Onboarding help"}},
            headers=headers_a,
        )
        assert r.status_code == 200, r.text

        r = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/leads", headers=headers_a
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        lead = body["items"][0]
        assert lead["email"] == "ada@example.com"
        assert lead["consent_given"] == 1
        assert lead["interest"] == "Onboarding help"

        r = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/leads/export",
            headers=headers_a,
        )
        assert r.status_code == 200, r.text
        assert "ada@example.com" in r.text

        # Another owner cannot read or write A's leads through B's workspace.
        r = await client.get(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/leads", headers=headers_b
        )
        assert r.status_code == 404, r.text
        r = await client.post(
            f"/workspaces/{ws_b}/agents/{agent_b['id']}/actions/{action['id']}/submit",
            json={"data": data},
            headers=headers_b,
        )
        assert r.status_code == 404, r.text

        # Missing consent is rejected by the dashboard form endpoint.
        r = await client.post(
            f"/workspaces/{ws_a}/agents/{agent_a['id']}/actions/{action['id']}/submit",
            json={"data": {**data, "_consent": False, "email": "new@example.com"}},
            headers=headers_a,
        )
        assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_data_collection_and_public_custom_form():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "standard")
        agent = await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/collections",
            json={
                "name": "Product feedback",
                "description": "Tell us what you think",
                "allow_partial": False,
                "require_consent": False,
                "fields": [
                    {"key": "full_name", "label": "Name", "type": "short_text", "required": True},
                    {"key": "email", "label": "Email", "type": "email", "required": True},
                    {"key": "rating", "label": "Rating", "type": "number", "required": True},
                    {"key": "feedback", "label": "Feedback", "type": "long_text", "required": False},
                ],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        collection = r.json()
        assert collection["submission_count"] == 0

        entry = await _action(
            client, headers, ws_id, agent["id"], "data_collection"
        )
        action = entry["action"]
        form = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/actions/{action['id']}/form",
            headers=headers,
        )
        assert form.status_code == 200, form.text
        assert {f["key"] for f in form.json()["fields"]} >= {"email", "rating"}

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/actions/{action['id']}/submit",
            json={
                "data": {
                    "full_name": "Neema",
                    "email": "neema@example.com",
                    "rating": 5,
                    "feedback": "Great service",
                }
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "submission"

        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/collections/{collection['id']}/submissions",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1

        # Custom form with a public token and consent checkbox.
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/forms",
            json={
                "title": "Request a quote",
                "description": "We reply within one business day.",
                "require_consent": True,
                "submit_label": "Request quote",
                "fields": [
                    {"key": "full_name", "label": "Name", "type": "short_text", "required": True},
                    {"key": "email", "label": "Email", "type": "email", "required": True},
                    {"key": "service", "label": "Service", "type": "select", "required": True, "options": ["Website", "Support"]},
                ],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        public_form = r.json()
        token = public_form["public_token"]

        r = await client.get(f"/public/forms/{token}")
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Request a quote"
        assert r.json()["require_consent"] == 1

        # Invalid select value is rejected.
        r = await client.post(
            f"/public/forms/{token}",
            json={
                "data": {
                    "full_name": "Baraka",
                    "email": "baraka@example.com",
                    "service": "Not an option",
                }
            },
        )
        assert r.status_code == 422, r.text

        # Consent is required.
        r = await client.post(
            f"/public/forms/{token}",
            json={
                "data": {
                    "full_name": "Baraka",
                    "email": "baraka@example.com",
                    "service": "Website",
                }
            },
        )
        assert r.status_code == 422, r.text

        r = await client.post(
            f"/public/forms/{token}",
            json={
                "data": {
                    "full_name": "Baraka",
                    "email": "baraka@example.com",
                    "service": "Website",
                    "_consent": True,
                }
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "complete"

        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/forms/{public_form['id']}/submissions",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1

        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/forms/{public_form['id']}/export",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert "baraka@example.com" in r.text

        # A downgraded workspace's public form stops accepting submissions.
        await _expire_trial(headers)
        async with get_db() as db:
            await db.execute(
                "UPDATE workspaces SET plan = 'free' WHERE id = ?", (ws_id,)
            )
            await db.commit()
        r = await client.get(f"/public/forms/{token}")
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_support_escalation_created_from_chat(monkeypatch):
    async def fake_retrieve(*_args, **_kwargs):
        return [], []

    monkeypatch.setattr(agent_chat_service, "_retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(
        agent_chat_service,
        "build_generator",
        lambda: _FakeGenerator("A team member will follow up with you."),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "standard")
        agent = await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/chat",
            json={"message": "I need to speak to a human about my order."},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"] == "A team member will follow up with you."
        assert any(
            item["action_type"] == "knowledge_support" for item in body["actions"]
        )

        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/escalations", headers=headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        assert r.json()["stats"]["open"] == 1
        escalation = r.json()["items"][0]

        r = await client.put(
            f"/workspaces/{ws_id}/agents/{agent['id']}/escalations/{escalation['id']}",
            json={"status": "contacted"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "contacted"


@pytest.mark.asyncio
async def test_chat_action_directive_returns_form_and_captures_lead(monkeypatch):
    async def fake_retrieve(*_args, **_kwargs):
        return [], []

    # The model asks for the interactive lead form.
    monkeypatch.setattr(agent_chat_service, "_retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(
        agent_chat_service,
        "build_generator",
        lambda: _FakeGenerator(
            "Happy to help — please share your details below.\n"
            '<botbase_action>{"type":"lead_capture","mode":"request_form"}</botbase_action>'
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "standard")
        agent = await _agent(client, headers, ws_id)

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/chat",
            json={"message": "I'd like a quote for my team."},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "<botbase_action>" not in body["answer"]
        assert body["action_form"] is not None
        assert body["action_form"]["action_type"] == "lead_capture"
        assert any(f["key"] == "email" for f in body["action_form"]["fields"])

        # The model submits already-provided data with explicit consent.
        monkeypatch.setattr(
            agent_chat_service,
            "build_generator",
            lambda: _FakeGenerator(
                "Thanks, I've saved your details.\n"
                '<botbase_action>{"type":"lead_capture","data":'
                '{"full_name":"Directive Lead","email":"directive@example.com","_consent":true}}'
                "</botbase_action>"
            ),
        )
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/chat",
            json={"message": "My email is directive@example.com — please contact me."},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert any(
            item["type"] == "lead_saved" for item in r.json()["actions"]
        )

        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/leads", headers=headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["email"] == "directive@example.com"


@pytest.mark.asyncio
async def test_email_agent_draft_approval_simulation(monkeypatch):
    async def fake_retrieve(*_args, **_kwargs):
        return [], []

    monkeypatch.setattr(agent_chat_service, "_retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(
        agent_chat_service,
        "build_generator",
        lambda: _FakeGenerator(
            "Hello John,\n\nThanks for your interest. Our team will share pricing shortly.\n\nBest regards"
        ),
    )
    from ..services import email_agent_service

    monkeypatch.setattr(
        email_agent_service,
        "build_generator",
        lambda: _FakeGenerator(
            "Hello John,\n\nThanks for your interest. Our team will share pricing shortly.\n\nBest regards"
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "standard")
        agent = await _agent(client, headers, ws_id)

        r = await client.put(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email",
            json={
                "provider": "simulated",
                "email_address": "sales@acme.test",
                "display_name": "Acme Sales",
                "automation_enabled": True,
                "notification_phone": "+255712000111",
                "filters": {},
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        integration = r.json()
        assert integration["provider"] == "simulated"
        assert integration["status"] == "simulation_ready"
        assert "credentials_encrypted" not in integration
        assert integration["has_credentials"] is False

        incoming = {
            "sender_name": "John Customer",
            "sender_email": "john@example.com",
            "subject": "Product inquiry",
            "body_text": "Hello, I would like to know your pricing.",
            "provider_message_id": "msg-1",
        }
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/simulate",
            json=incoming,
            headers=headers,
        )
        assert r.status_code == 201, r.text
        result = r.json()
        draft = result["draft"]
        assert draft["status"] == "draft_ready"
        assert "John" in draft["body"]
        assert draft["sent_simulated"] == 0

        # The simulated SMS alert is stored, not sent.
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/notifications",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["sms_mode"] == "simulated"
        assert r.json()["items"][0]["status"] == "simulated"
        assert "Product inquiry" in r.json()["items"][0]["body"]

        # Re-delivering the same provider id does not create a second draft.
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/simulate",
            json=incoming,
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["duplicate"] is True

        # Explicit confirmation is required.
        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/drafts/{draft['id']}/approve",
            json={"confirm_simulated_send": False},
            headers=headers,
        )
        assert r.status_code == 422, r.text

        r = await client.post(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/drafts/{draft['id']}/approve",
            json={
                "confirm_simulated_send": True,
                "body": "Hello John,\n\nOur pricing starts at TZS 50,000.\n\nBest regards",
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        approved = r.json()
        assert approved["status"] == "sent"
        assert approved["sent_simulated"] == 1
        assert approved["sent_at"]
        assert "TZS 50,000" in approved["body"]

        # The audit trail records the sensitive approval.
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/audit", headers=headers
        )
        assert r.status_code == 200, r.text
        assert any("approved" in item["action"] for item in r.json()["items"])

        # Another owner cannot see this mailbox or its drafts.
        headers_b = await _register(client)
        ws_b = await _workspace(client, headers_b, "standard")
        agent_b = await _agent(client, headers_b, ws_b)
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email", headers=headers_b
        )
        assert r.status_code == 404, r.text
        r = await client.get(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email/drafts/{draft['id']}",
            headers=headers_b,
        )
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_email_agent_requires_standard_plan():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await _register(client)
        ws_id = await _workspace(client, headers, "free")
        agent = await _agent(client, headers, ws_id)
        r = await client.put(
            f"/workspaces/{ws_id}/agents/{agent['id']}/email",
            json={
                "provider": "simulated",
                "email_address": "free@acme.test",
            },
            headers=headers,
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "plan_feature_locked"
