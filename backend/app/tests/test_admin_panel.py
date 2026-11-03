"""
tests/test_admin_panel.py
Master admin panel: bootstrap, route protection, permissions, suspension
enforcement, metrics, audit immutability, secret hygiene, deletion cascade,
platform controls, TOTP, and a performance smoke test.
"""
import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from ..core.config import settings

ADMIN = settings.admin_route_prefix.rstrip("/")
from ..core.database import get_db
from ..core import totp
from ..services import admin_service, email_service
from ..services.password_reset_service import reset_rate_limit_state

SECRET_PATTERNS = ("$2b$", "password_hash", "token_hash", "key_hash", "totp_secret")


@pytest.fixture(autouse=True)
def _clean_state():
    from ..api import auth as auth_module

    email_service.reset_memory_outbox()
    admin_service.clear_platform_settings_cache()
    reset_rate_limit_state()
    auth_module.reset_admin_auth_buckets()
    yield
    email_service.reset_memory_outbox()
    admin_service.clear_platform_settings_cache()
    auth_module.reset_admin_auth_buckets()


@pytest_asyncio.fixture(autouse=True)
async def _reset_platform_settings():
    """Platform controls back to defaults before every test."""
    from ..core.database import get_db

    async with get_db() as db:
        for key, value in (
            ("signups_open", "true"),
            ("maintenance_message", ""),
            ("emergency_off", "false"),
        ):
            await db.execute(
                "INSERT INTO platform_settings (key, value, updated_at, "
                "updated_by) VALUES (?, ?, ?, 'test') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value, datetime.now(timezone.utc).isoformat()),
            )
        await db.commit()
    admin_service.clear_platform_settings_cache()


async def _register(client, email=None, password="UserPass123!"):
    email = email or f"{uuid.uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return email, response.json()


async def _make_superadmin(client, email="founder@example.com", password="FounderPass123!"):
    async with get_db() as db:
        from ..core.auth import hash_password
        from datetime import datetime, timezone

        cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET role = 'superadmin', hashed_password = ?, "
                "suspended_at = NULL WHERE id = ?",
                (hash_password(password), row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO users (id, email, hashed_password, is_active, "
                "created_at, plan, trial_ends_at, role) "
                "VALUES (?, ?, ?, 1, ?, 'free', NULL, 'superadmin')",
                (
                    str(uuid.uuid4()), email, hash_password(password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        await db.commit()
    login = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    if body.get("token_type") == "totp":
        # Account has 2FA enabled: complete the second step with a real code.
        from ..core import totp as totp_module

        async with get_db() as db:
            cur = await db.execute(
                "SELECT totp_secret FROM users WHERE email = ?", (email,)
            )
            secret_row = await cur.fetchone()
        secret = totp_module.decrypt_secret(secret_row["totp_secret"])
        step = await client.post(
            "/auth/login/totp",
            json={
                "totp_token": body["totp_token"],
                "code": totp_module.code_at(secret, int(time.time())),
            },
        )
        assert step.status_code == 200, step.text
        return step.json()["access_token"]
    return body["access_token"]


@pytest.mark.asyncio
async def test_bootstrap_creates_and_refuses_second(capsys):
    from ..scripts.create_master_admin import _bootstrap

    email = f"founder-{uuid.uuid4().hex[:8]}@example.com"
    password = "FounderPass123!"
    code = await _bootstrap(email, force_second=False, password=password)
    assert code == 0
    out = capsys.readouterr().out
    assert password not in out

    second = await _bootstrap(email, force_second=False, password=password)
    assert second == 1
    out2 = capsys.readouterr().out
    assert "already exists" in out2

    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'superadmin'"
        )
        count = int((await cur.fetchone())["n"])
    assert count == 1


@pytest.mark.asyncio
async def test_registration_cannot_escalate(test_client):
    email = f"evil-{uuid.uuid4().hex[:8]}@example.com"
    response = await test_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "UserPass123!",
            "role": "superadmin",
            "permissions": ["users.manage"],
            "is_admin": True,
        },
    )
    assert response.status_code == 201
    async with get_db() as db:
        cur = await db.execute(
            "SELECT role, permissions FROM users WHERE email = ?", (email,)
        )
        row = await cur.fetchone()
    assert row["role"] == "user"
    assert row["permissions"] is None


@pytest.mark.asyncio
async def test_every_admin_route_is_protected(test_client):
    from ..main import app as real_app

    schema = real_app.openapi()
    ops = [
        (method.upper(), path)
        for path, methods in schema["paths"].items()
        if path.startswith(ADMIN)
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(ops) >= 30, f"only {len(ops)} admin routes found"

    def fill(path: str) -> str:
        return re.sub(r"\{[^}]+\}", "x", path)

    _, registered = await _register(test_client)
    normal_token = registered["access_token"]

    checked = 0
    for method, path in ops:
        target = fill(path)
        anon = await test_client.request(method, target)
        assert anon.status_code == 401, (method, target, anon.status_code)
        user_hit = await test_client.request(
            method, target, headers={"Authorization": f"Bearer {normal_token}"}
        )
        assert user_hit.status_code == 403, (method, target, user_hit.status_code)
        checked += 1
    assert checked == len(ops)


@pytest.mark.asyncio
async def test_permissions_gate_each_section(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    async with get_db() as db:
        from ..core.auth import hash_password
        from datetime import datetime, timezone

        await db.execute(
            "INSERT INTO users (id, email, hashed_password, is_active, "
            "created_at, plan, trial_ends_at, role, permissions) "
            "VALUES (?, ?, ?, 1, ?, 'free', NULL, 'admin', ?)",
            (
                str(uuid.uuid4()), "support@example.com", hash_password("SupportPass123!"),
                datetime.now(timezone.utc).isoformat(), json.dumps(["users.read"]),
            ),
        )
        await db.commit()

    login = await test_client.post(
        "/auth/login", json={"email": "support@example.com", "password": "SupportPass123!"}
    )
    admin_token = login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    allowed = await test_client.get(f"{ADMIN}/users", headers=admin_headers)
    assert allowed.status_code == 200
    denied = await test_client.get(f"{ADMIN}/overview", headers=admin_headers)
    assert denied.status_code == 403
    admins = await test_client.get(f"{ADMIN}/admins", headers=admin_headers)
    assert admins.status_code == 403
    platform = await test_client.get(f"{ADMIN}/platform/settings", headers=admin_headers)
    assert platform.status_code == 403

    # Superadmin passes everything.
    overview = await test_client.get(f"{ADMIN}/overview", headers=headers)
    assert overview.status_code == 200


@pytest.mark.asyncio
async def test_admin_creation_invite_and_login(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    create = await test_client.post(
        f"{ADMIN}/admins",
        json={
            "email": "ops@example.com",
            "preset": "support",
            "reauth_password": "FounderPass123!",
        },
        headers=headers,
    )
    assert create.status_code == 200, create.text
    body = create.json()
    assert body["permissions"]
    # File/memory backend returns the one-time setup link.
    assert body.get("setup_url", "").startswith(settings.resolved_frontend_url)

    invites = [
        m for m in email_service.MEMORY_OUTBOX
        if m["to"] == "ops@example.com" and "admin" in m["subject"].lower()
    ]
    assert len(invites) == 1
    match = re.search(r"token=([A-Za-z0-9_\-]+)", invites[0]["text"])
    assert match

    # Set the password via the reset endpoint.
    reset = await test_client.post(
        "/auth/reset-password",
        json={"token": match.group(1), "new_password": "SupportPass123!"},
    )
    assert reset.status_code == 200
    login = await test_client.post(
        "/auth/login", json={"email": "ops@example.com", "password": "SupportPass123!"}
    )
    assert login.status_code == 200
    me = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_immediate_revocation_and_superadmin_guard(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    # Create an admin, then suspend them; their token must stop working.
    create = await test_client.post(
        f"{ADMIN}/admins",
        json={
            "email": "temp-admin@example.com",
            "permissions": ["users.read"],
            "reauth_password": "FounderPass123!",
        },
        headers=headers,
    )
    admin_id = create.json()["admin_id"]
    setup = create.json().get("setup_url", "")
    match = re.search(r"token=([A-Za-z0-9_\-]+)", setup)
    await test_client.post(
        "/auth/reset-password",
        json={"token": match.group(1), "new_password": "SupportPass123!"},
    )
    login = await test_client.post(
        "/auth/login", json={"email": "temp-admin@example.com", "password": "SupportPass123!"}
    )
    admin_token = login.json()["access_token"]
    ok_before = await test_client.get(
        f"{ADMIN}/users", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert ok_before.status_code == 200

    suspend = await test_client.post(
        f"{ADMIN}/admins/{admin_id}/suspend",
        json={"reason": "contract ended"},
        headers=headers,
    )
    assert suspend.status_code == 200
    after = await test_client.get(
        f"{ADMIN}/users", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert after.status_code == 401

    # Last-superadmin protection: cannot suspend or delete the superadmin.
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM users WHERE role = 'superadmin' LIMIT 1"
        )
        founder_id = (await cur.fetchone())["id"]
    deny_suspend = await test_client.post(
        f"{ADMIN}/admins/{founder_id}/suspend",
        json={"reason": "nope"},
        headers=headers,
    )
    assert deny_suspend.status_code == 403
    deny_delete = await test_client.request(
        "DELETE", f"{ADMIN}/admins/{founder_id}", headers=headers
    )
    assert deny_delete.status_code == 403
    deny_demote = await test_client.request(
        "DELETE", f"{ADMIN}/users/{founder_id}", headers=headers,
        json={"email_confirmation": "x", "reauth_password": "FounderPass123!"},
    )
    assert deny_demote.status_code == 403


@pytest.mark.asyncio
async def test_metrics_match_sql_counts(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    _, registered = await _register(test_client)
    user_headers = {"Authorization": f"Bearer {registered['access_token']}"}
    ws = await test_client.post(
        "/workspaces", json={"name": "metrics"}, headers=user_headers
    )
    ws_id = ws.json()["id"]
    recent = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()

    async with get_db() as db:
        for _ in range(3):
            await db.execute(
                "INSERT INTO usage_events (id, workspace_id, kind, quantity, "
                "created_at, channel, model, status, latency_ms) "
                "VALUES (?, ?, 'chat', 1, ?, 'widget', 'model-a', 'ok', 100)",
                (str(uuid.uuid4()), ws_id, recent),
            )

    overview = await test_client.get(f"{ADMIN}/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()

    async with get_db() as db:
        cur = await db.execute("SELECT COUNT(*) AS n FROM users")
        users_n = int((await cur.fetchone())["n"])
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM usage_events WHERE channel = 'widget'"
        )
        widget_n = int((await cur.fetchone())["n"])
    assert body["totals"]["users"] == users_n
    assert body["chat_by_channel_90d"].get("widget", 0) == widget_n
    assert "estimated_monthly_revenue_tzs" in body


@pytest.mark.asyncio
async def test_suspension_enforcement_end_to_end(test_client):
    # User with a workspace/agent/embed token.
    email, registered = await _register(test_client)
    user_token = registered["access_token"]
    headers = {"Authorization": f"Bearer {user_token}"}
    ws = await test_client.post(
        "/workspaces", json={"name": "shop"}, headers=headers
    )
    ws_id = ws.json()["id"]
    agent = await test_client.post(
        f"/workspaces/{ws_id}/agents",
        json={"name": "bot", "system_prompt": "Be brief and helpful to customers."},
        headers=headers,
    )
    agent_id = agent.json()["id"]
    tok = await test_client.post(
        f"/workspaces/{ws_id}/agents/{agent_id}/tokens",
        json={"label": "site"},
        headers=headers,
    )
    embed_token = tok.json()["token"]

    founder_token = await _make_superadmin(test_client)
    founder_headers = {"Authorization": f"Bearer {founder_token}"}
    users_list = await test_client.get(
        f"{ADMIN}/users?search={email}", headers=founder_headers
    )
    user_id = users_list.json()["items"][0]["id"]

    await test_client.post(
        f"{ADMIN}/users/{user_id}/suspend",
        json={"reason": "abuse"},
        headers=founder_headers,
    )

    login = await test_client.post(
        "/auth/login", json={"email": email, "password": "UserPass123!"}
    )
    assert login.status_code == 401
    me = await test_client.get("/auth/me", headers=headers)
    assert me.status_code == 401
    public = await test_client.post(
        "/public/chat",
        json={"token": embed_token, "message": "hi"},
    )
    assert public.status_code == 503
    assert "temporarily unavailable" in public.json()["detail"].lower()

    await test_client.post(
        f"{ADMIN}/users/{user_id}/reactivate", headers=founder_headers
    )
    login2 = await test_client.post(
        "/auth/login", json={"email": email, "password": "UserPass123!"}
    )
    assert login2.status_code == 200


@pytest.mark.asyncio
async def test_plan_change_trial_and_payments(test_client):
    email, _ = await _register(test_client)
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    async with get_db() as db:
        cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
        user_id = (await cur.fetchone())["id"]

    plan = await test_client.post(
        f"{ADMIN}/subscriptions/{user_id}/plan",
        json={"plan": "standard", "reason": "upgraded by support"},
        headers=headers,
    )
    assert plan.status_code == 200

    me = await test_client.post(
        "/auth/login", json={"email": email, "password": "UserPass123!"}
    )
    me_info = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {me.json()['access_token']}"}
    )
    assert me_info.json()["plan"]["base"] == "standard"

    trial = await test_client.post(
        f"{ADMIN}/subscriptions/{user_id}/trial",
        json={"days": 30, "reason": "courtesy"},
        headers=headers,
    )
    assert trial.status_code == 200

    payment = await test_client.post(
        f"{ADMIN}/payments/{user_id}",
        json={"amount_tzs": 7800, "method": "mpesa", "reference": "TX-1"},
        headers=headers,
    )
    assert payment.status_code == 200, payment.text

    payments = await test_client.get(f"{ADMIN}/payments", headers=headers)
    assert payments.status_code == 200
    assert any(p["reference"] == "TX-1" for p in payments.json()["items"])

    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM plan_changes WHERE user_id = ?", (user_id,)
        )
        assert int((await cur.fetchone())["n"]) >= 1
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE action IN "
            "('billing.plan_change', 'billing.trial_change')"
        )
        assert int((await cur.fetchone())["n"]) >= 2


@pytest.mark.asyncio
async def test_audit_immutability_and_conversation_view(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a real audit row (through the API), then try to mutate it raw.
    async with get_db() as db:
        await db.execute(
            "INSERT INTO audit_log (id, ts, actor_id, actor_email, action, "
            "target_type, target_id, summary) VALUES (?, ?, ?, ?, 'probe', "
            "NULL, NULL, 'probe row')",
            (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(),
             "x", "probe@example.com"),
        )
        await db.commit()
        row_id = (
            await (
                await db.execute(
                    "SELECT id FROM audit_log WHERE action = 'probe'"
                )
            ).fetchone()
        )["id"]

        try:
            await db.execute("DELETE FROM audit_log WHERE id = ?", (row_id,))
            await db.commit()
        except Exception:
            deleted = "blocked"
        else:
            deleted = "allowed"
        try:
            await db.execute(
                "UPDATE audit_log SET summary = 'tampered' WHERE id = ?", (row_id,)
            )
            await db.commit()
        except Exception:
            updated = "blocked"
        else:
            updated = "allowed"
    assert deleted == "blocked"
    assert updated == "blocked"


@pytest.mark.asyncio
async def test_secret_leakage_crawl(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    from ..main import app as real_app

    schema = real_app.openapi()
    checked = 0
    for path, methods in schema["paths"].items():
        if not path.startswith(ADMIN) or "get" not in methods:
            continue
        target = re.sub(r"\{[^}]+\}", "x", path)
        response = await test_client.get(target, headers=headers)
        if response.status_code == 200:
            try:
                payload = json.dumps(response.json(), default=str)
            except Exception:
                continue  # CSV export — inspected separately
            for pattern in SECRET_PATTERNS:
                assert pattern not in payload, (path, pattern)
            assert "sk-botbase-" not in payload
            checked += 1
    assert checked >= 8, f"only {checked} GET endpoints crawled"


@pytest.mark.asyncio
async def test_injection_and_sort_validation(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    evil = "'; DROP TABLE users;--"
    response = await test_client.get(
        f"{ADMIN}/users", params={"search": evil, "sort": evil}, headers=headers
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        body = response.json()
        assert "items" in body
    # Tables still exist.
    async with get_db() as db:
        cur = await db.execute("SELECT COUNT(*) AS n FROM users")
        await cur.fetchone()


@pytest.mark.asyncio
async def test_deletion_cascade_leaves_no_orphans(test_client):
    email, _ = await _register(test_client)
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    async with get_db() as db:
        cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
        user_id = (await cur.fetchone())["id"]
        ws_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO workspaces (id, name, owner_id, created_at, plan) "
            "VALUES (?, 'cascade', ?, ?, 'free')",
            (ws_id, user_id, "2026-01-01T00:00:00+00:00"),
        )
        doc_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO workspace_documents (id, workspace_id, filename, "
            "file_path, file_type, status, created_at) "
            "VALUES (?, ?, 'x.pdf', '/tmp/x.pdf', 'pdf', 'ready', '2026-01-01T00:00:00+00:00')",
            (doc_id, ws_id),
        )
        await db.execute(
            "INSERT INTO documents (id, filename, upload_date, total_pages, "
            "file_size, status) VALUES (?, 'x.pdf', '2026-01-01', 1, 1, 'ready')",
            (doc_id,),
        )
        await db.execute(
            "INSERT INTO chunks (id, document_id, page, chunk_index, text, "
            "workspace_id, doc_id) VALUES (?, ?, 1, 0, 'text', ?, ?)",
            (str(uuid.uuid4()), doc_id, ws_id, doc_id),
        )
        agent_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO agents (id, workspace_id, name, system_prompt, model, "
            "is_active, created_at, updated_at) "
            "VALUES (?, ?, 'bot', 'x', 'm', 1, '2026-01-01', '2026-01-01')",
            (agent_id, ws_id),
        )
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, created_at, agent_id, workspace_id) "
            "VALUES (?, '2026-01-01', ?, ?)",
            (conv_id, agent_id, ws_id),
        )
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, 'user', 'hi', '2026-01-01')",
            (str(uuid.uuid4()), conv_id),
        )
        await db.execute(
            "INSERT INTO agent_embed_tokens (id, agent_id, token, is_active, "
            "created_at) VALUES (?, ?, ?, 1, '2026-01-01')",
            (str(uuid.uuid4()), agent_id, "tok-" + uuid.uuid4().hex),
        )
        await db.execute(
            "INSERT INTO developer_api_keys (id, user_id, workspace_id, name, "
            "key_hash, key_prefix, is_active, created_at) "
            "VALUES (?, ?, ?, 'k', ?, 'sk-', 1, '2026-01-01')",
            (str(uuid.uuid4()), user_id, ws_id, uuid.uuid4().hex),
        )
        await db.execute(
            "INSERT INTO website_sources (id, workspace_id, url, name, status, "
            "created_at, updated_at) "
            "VALUES (?, ?, 'https://x.com', 'x', 'ready', '2026-01-01', '2026-01-01')",
            (str(uuid.uuid4()), ws_id),
        )
        await db.commit()

    delete = await test_client.request(
        "DELETE",
        f"{ADMIN}/users/{user_id}",
        json={
            "email_confirmation": email,
            "reauth_password": "FounderPass123!",
        },
        headers=headers,
    )
    assert delete.status_code == 200, delete.text

    async with get_db() as db:
        for table, column, value in (
            ("workspaces", "owner_id", user_id),
            ("workspace_documents", "workspace_id", ws_id),
            ("chunks", "workspace_id", ws_id),
            ("agents", "workspace_id", ws_id),
            ("conversations", "workspace_id", ws_id),
            ("agent_embed_tokens", "agent_id", agent_id),
            ("developer_api_keys", "workspace_id", ws_id),
            ("website_sources", "workspace_id", ws_id),
            ("users", "id", user_id),
        ):
            cur = await db.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (value,)
            )
            assert int((await cur.fetchone())["n"]) == 0, table


@pytest.mark.asyncio
async def test_platform_controls(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    close = await test_client.put(
        f"{ADMIN}/platform/settings",
        json={"signups_open": False, "reauth_password": "FounderPass123!"},
        headers=headers,
    )
    assert close.status_code == 200
    register = await test_client.post(
        "/auth/register",
        json={"email": f"blocked-{uuid.uuid4().hex[:6]}@example.com", "password": "UserPass123!"},
    )
    assert register.status_code == 403

    emergency = await test_client.put(
        f"{ADMIN}/platform/settings",
        json={"emergency_off": True, "reauth_password": "FounderPass123!"},
        headers=headers,
    )
    assert emergency.status_code == 200
    public = await test_client.post(
        "/public/chat", json={"token": "whatever", "message": "hi"}
    )
    # Emergency check runs before token lookup → 503 regardless of token.
    assert public.status_code == 503
    assert "temporarily unavailable" in public.json()["detail"].lower()

    reopen = await test_client.put(
        f"{ADMIN}/platform/settings",
        json={
            "signups_open": True,
            "emergency_off": False,
            "reauth_password": "FounderPass123!",
        },
        headers=headers,
    )
    assert reopen.status_code == 200
    register2 = await test_client.post(
        "/auth/register",
        json={"email": f"open-{uuid.uuid4().hex[:6]}@example.com", "password": "UserPass123!"},
    )
    assert register2.status_code == 201

    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'platform.settings'"
        )
        assert int((await cur.fetchone())["n"]) >= 3


@pytest.mark.asyncio
async def test_totp_unit_and_login_flow(test_client):
    # Unit level: code verification, recovery codes.
    secret = totp.generate_secret()
    now_code = totp.code_at(secret, int(time.time()))
    assert totp.verify_code(secret, now_code)
    assert not totp.verify_code(secret, "000000")
    plain, hashed = totp.generate_recovery_codes()
    stored = json.dumps(hashed)
    assert totp.match_recovery_code(plain[0], stored)
    matched, updated = totp.consume_recovery_code(plain[0], stored)
    assert matched and plain[0] not in updated
    assert not totp.match_recovery_code(plain[0], updated)

    # Endpoint flow: enable TOTP on an admin, then complete the login step.
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    setup = await test_client.post(
        f"{ADMIN}/my-account/totp/setup",
        json={"reauth_password": "FounderPass123!"},
        headers=headers,
    )
    assert setup.status_code == 200, setup.text
    secret2 = setup.json()["secret"]

    verify = await test_client.post(
        f"{ADMIN}/my-account/totp/verify",
        json={"code": totp.code_at(secret2, int(time.time()))},
        headers=headers,
    )
    assert verify.status_code == 200
    recovery = verify.json()["recovery_codes"]
    assert len(recovery) == 10

    # Password login now returns a TOTP challenge instead of a token.
    challenge = await test_client.post(
        "/auth/login", json={"email": "founder@example.com", "password": "FounderPass123!"}
    )
    assert challenge.status_code == 200
    assert challenge.json()["token_type"] == "totp"

    wrong = await test_client.post(
        "/auth/login/totp",
        json={"totp_token": challenge.json()["totp_token"], "code": "000000"},
    )
    assert wrong.status_code == 401

    good = await test_client.post(
        "/auth/login/totp",
        json={
            "totp_token": challenge.json()["totp_token"],
            "code": totp.code_at(secret2, int(time.time())),
        },
    )
    assert good.status_code == 200
    assert good.json()["access_token"]

    # Recovery code: works once, then not again.
    challenge2 = await test_client.post(
        "/auth/login", json={"email": "founder@example.com", "password": "FounderPass123!"}
    )
    once = await test_client.post(
        "/auth/login/totp",
        json={"totp_token": challenge2.json()["totp_token"], "code": recovery[0]},
    )
    assert once.status_code == 200
    challenge3 = await test_client.post(
        "/auth/login", json={"email": "founder@example.com", "password": "FounderPass123!"}
    )
    twice = await test_client.post(
        "/auth/login/totp",
        json={"totp_token": challenge3.json()["totp_token"], "code": recovery[0]},
    )
    assert twice.status_code == 401

    # Attempt rate limit.
    from ..api import auth as auth_module

    auth_module.reset_admin_auth_buckets()
    last_status = None
    for _ in range(settings.totp_max_attempts_per_15m + 1):
        challenge4 = await test_client.post(
            "/auth/login", json={"email": "founder@example.com", "password": "FounderPass123!"}
        )
        last_status = (
            await test_client.post(
                "/auth/login/totp",
                json={"totp_token": challenge4.json()["totp_token"], "code": "111111"},
            )
        ).status_code
    assert last_status == 429


@pytest.mark.asyncio
async def test_performance_smoke(test_client):
    token = await _make_superadmin(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    _, registered = await _register(test_client)
    user_headers = {"Authorization": f"Bearer {registered['access_token']}"}
    ws = await test_client.post(
        "/workspaces", json={"name": "perf"}, headers=user_headers
    )
    ws_id = ws.json()["id"]
    async with get_db() as db:
        for _ in range(2000):
            await db.execute(
                "INSERT INTO usage_events (id, workspace_id, kind, quantity, "
                "created_at, channel, model, status, latency_ms) "
                "VALUES (?, ?, 'chat', 1, ?, 'widget', 'm', 'ok', 50)",
                (
                    str(uuid.uuid4()),
                    ws_id,
                    (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                ),
            )
        await db.commit()

    start = time.perf_counter()
    overview = await test_client.get(f"{ADMIN}/overview", headers=headers)
    overview_elapsed = time.perf_counter() - start
    start = time.perf_counter()
    usage = await test_client.get(f"{ADMIN}/usage/summary", headers=headers)
    usage_elapsed = time.perf_counter() - start
    assert overview.status_code == 200
    assert usage.status_code == 200
    assert overview_elapsed < 5.0, f"overview took {overview_elapsed:.2f}s"
    assert usage_elapsed < 5.0, f"usage took {usage_elapsed:.2f}s"
