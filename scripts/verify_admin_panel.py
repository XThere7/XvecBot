#!/usr/bin/env python3
"""
verify_admin_panel.py
End-to-end verification of the master admin panel against a live server.

Run inside the backend environment, e.g.:

    docker exec -w /app/backend botbase-api-5434 \
        env PYTHONPATH=/app/backend python /app/scripts/verify_admin_panel.py

Spawns its own throwaway uvicorn (file email backend, clean outbox, scratch
SQLite), bootstraps the superadmin via the CLI (password on stdin, never
echoed), then exercises: route protection, permissions, invites, immediate
revocation, metrics, suspension enforcement, plan/trial/payment flows,
audit immutability, secret hygiene, deletion cascade, platform controls,
TOTP login flow and a 20k-row performance check.
"""
from __future__ import annotations

import asyncio
import email.parser
import email.policy
import hashlib
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_CANDIDATES = [Path("/app/backend"), _SCRIPT_DIR.parent / "backend"]
ROOT = next(
    (c for c in _BACKEND_CANDIDATES if (c / "app" / "main.py").exists()),
    _SCRIPT_DIR.parent / "backend",
)
from app.core.config import settings  # noqa: E402
from app.core import totp  # noqa: E402

FRONTEND_URL = "http://localhost:3000"
ADMIN = settings.admin_route_prefix.rstrip("/")
FOUNDER_EMAIL = "founder@example.com"
FOUNDER_PASSWORD = "FounderPass123!"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def base_env(tmp: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": f"sqlite:///{tmp / 'rag.db'}",
        "UPLOAD_DIR": str(tmp / "uploads"),
        "EMAIL_BACKEND": "file",
        "EMAIL_OUTBOX_DIR": str(tmp / "outbox"),
        "EMAIL_FROM_ADDRESS": "botbasex7@gmail.com",
        "EMAIL_FROM_NAME": "BotBase",
        "EMAIL_REPLY_TO": "botbasex7@gmail.com",
        "SUPPORT_EMAIL": "botbasex7@gmail.com",
        "FRONTEND_URL": FRONTEND_URL,
        "DOCS_URL": f"{FRONTEND_URL}/docs",
        "DEBUG": "true",
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(24),
        "DEFAULT_WORKSPACE_PLAN": "free",
        "OPENROUTER_API_KEY": "",
        "LOG_LEVEL": "WARNING",
    }


def start_server(tmp: Path) -> tuple[subprocess.Popen, int, Path]:
    port = free_port()
    env = {**os.environ, **base_env(tmp)}
    env["PYTHONPATH"] = str(ROOT)
    log_path = tmp / "server.log"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=ROOT,
        env=env,
        stdout=open(log_path, "ab"),
        stderr=subprocess.STDOUT,
    )
    return process, port, log_path


def wait_health(port: int, timeout: float = 300.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("server did not become healthy in time")


def bootstrap(tmp: Path, email: str = FOUNDER_EMAIL, password: str = FOUNDER_PASSWORD) -> str:
    """Run the bootstrap CLI with the password on stdin; return its output."""
    env = {**os.environ, **base_env(tmp)}
    env["PYTHONPATH"] = str(ROOT)
    process = subprocess.run(
        [sys.executable, "-m", "app.scripts.create_master_admin",
         "--email", email, "--stdin"],
        cwd=ROOT,
        env=env,
        input=f"{password}\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    return process.stdout + process.stderr


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="botbase-admin-verify-"))
    (tmp / "outbox").mkdir(exist_ok=True)
    server: subprocess.Popen | None = None
    try:
        print(f"Verification workspace: {tmp}")
        server, port, log_path = start_server(tmp)
        wait_health(port)
        base = f"http://127.0.0.1:{port}"

        # ── 1. Bootstrap ──────────────────────────────────────────────────────
        out1 = bootstrap(tmp)
        check("Bootstrap creates the superadmin", "Master admin created" in out1 or "Master admin promoted" in out1)
        check("Bootstrap never echoes the password", FOUNDER_PASSWORD not in out1)
        out2 = bootstrap(tmp, "second@example.com", "SecondPass123!")
        check("Bootstrap refuses a second superadmin", "already exists" in out2)
        logs = log_path.read_text(errors="ignore")
        check("Password appears nowhere in server logs", FOUNDER_PASSWORD not in logs)

        login = httpx.post(f"{base}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD}, timeout=60)
        check("Superadmin can sign in", login.status_code == 200, f"status={login.status_code}")
        super_token = login.json()["access_token"]
        sh = {"Authorization": f"Bearer {super_token}"}

        # ── 3. Route protection harness ───────────────────────────────────────
        schema = httpx.get(f"{base}/openapi.json", timeout=60).json()
        ops = [
            (m.upper(), p)
            for p, v in schema["paths"].items()
            if p.startswith(ADMIN)
            for m in v
            if m in {"get", "post", "put", "patch", "delete"}
        ]
        def fill(path: str) -> str:
            return re.sub(r"\{[^}]+\}", "x", path)

        reg = httpx.post(
            f"{base}/auth/register",
            json={"email": f"normal-{uuid.uuid4().hex[:8]}@example.com", "password": "NormalPass123!"},
            timeout=60,
        )
        normal_token = reg.json()["access_token"]
        failures = 0
        for method, path in ops:
            target = fill(path)
            anon = httpx.request(method, base + target, timeout=60)
            if anon.status_code != 401:
                failures += 1
            user_hit = httpx.request(
                method, base + target,
                headers={"Authorization": f"Bearer {normal_token}"}, timeout=60,
            )
            if user_hit.status_code != 403:
                failures += 1
        check(
            "Every /admin route returns 401 anon and 403 for normal users",
            failures == 0,
            f"routes={len(ops)} failures={failures}",
        )
        print(f"  route count: {len(ops)}")

        # ── 4. Permissions ────────────────────────────────────────────────────
        create = httpx.post(
            f"{base}{ADMIN}/admins",
            json={"email": "support@example.com", "permissions": ["users.read"],
                  "reauth_password": FOUNDER_PASSWORD},
            headers=sh, timeout=60,
        )
        check("Superadmin creates an admin", create.status_code == 200, create.text[:120])
        setup_url = create.json().get("setup_url", "")
        match = re.search(r"token=([A-Za-z0-9_\-]+)", setup_url)
        check("Admin invite exposes a one-time setup link", bool(match))
        invite_reset = httpx.post(
            f"{base}/auth/reset-password",
            json={"token": match.group(1), "new_password": "SupportPass123!"}, timeout=60,
        )
        check("Invite link sets the admin password", invite_reset.status_code == 200)
        outbox = list((tmp / "outbox").glob("*.eml"))
        check("Invite email written to the outbox", len(outbox) >= 1)
        admin_login = httpx.post(
            f"{base}/auth/login", json={"email": "support@example.com", "password": "SupportPass123!"}, timeout=60
        )
        check("New admin can sign in", admin_login.status_code == 200)
        ah = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        check("Admin can use a permitted route", httpx.get(f"{base}{ADMIN}/users", headers=ah, timeout=60).status_code == 200)
        check("Admin is denied overview without permission", httpx.get(f"{base}{ADMIN}/overview", headers=ah, timeout=60).status_code == 403)
        check("Admin is denied admins and platform", httpx.get(f"{base}{ADMIN}/admins", headers=ah, timeout=60).status_code == 403)

        # ── 6. Immediate revocation ───────────────────────────────────────────
        admins_list = httpx.get(f"{base}{ADMIN}/admins", headers=sh, timeout=60).json()
        support_id = next(a["id"] for a in admins_list["items"] if a["email"] == "support@example.com")
        httpx.post(f"{base}{ADMIN}/admins/{support_id}/suspend", json={"reason": "revoked"}, headers=sh, timeout=60)
        check("Suspended admin's token stops working", httpx.get(f"{base}{ADMIN}/users", headers=ah, timeout=60).status_code == 401)

        # ── 7. Last-superadmin protection ─────────────────────────────────────
        founders = [a for a in admins_list["items"] if a["role"] == "superadmin"]
        founder_suspend = httpx.post(
            f"{base}{ADMIN}/admins/{founders[0]['id']}/suspend",
            json={"reason": "cannot suspend master"}, headers=sh, timeout=60,
        )
        check("Superadmin cannot be suspended by API", founder_suspend.status_code == 403, f"status={founder_suspend.status_code}")

        # ── 8. Metric correctness ─────────────────────────────────────────────
        overview = httpx.get(f"{base}{ADMIN}/overview", headers=sh, timeout=60)
        check("Overview renders", overview.status_code == 200)
        body = overview.json()
        db_path = tmp / "rag.db"
        with sqlite3.connect(db_path) as conn:
            users_n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        check("Overview user total equals SQL count", body["totals"]["users"] == users_n, f"api={body['totals']['users']} sql={users_n}")

        # ── 9. Suspension enforcement ─────────────────────────────────────────
        cust_email = f"cust-{uuid.uuid4().hex[:8]}@example.com"
        cust_reg = httpx.post(f"{base}/auth/register", json={"email": cust_email, "password": "CustPass123!"}, timeout=60)
        cust_token = cust_reg.json()["access_token"]
        ch = {"Authorization": f"Bearer {cust_token}"}
        ws = httpx.post(f"{base}/workspaces", json={"name": "shop"}, headers=ch, timeout=60).json()
        agent = httpx.post(
            f"{base}/workspaces/{ws['id']}/agents",
            json={"name": "bot", "system_prompt": "Be brief and helpful to customers."},
            headers=ch, timeout=60,
        ).json()
        embed = httpx.post(
            f"{base}/workspaces/{ws['id']}/agents/{agent['id']}/tokens",
            json={"label": "site"}, headers=ch, timeout=60,
        ).json()["token"]
        users_page = httpx.get(f"{base}{ADMIN}/users", params={"search": cust_email}, headers=sh, timeout=60).json()
        cust_id = users_page["items"][0]["id"]
        httpx.post(f"{base}{ADMIN}/users/{cust_id}/suspend", json={"reason": "abuse"}, headers=sh, timeout=60)
        check("Suspended user cannot log in", httpx.post(f"{base}/auth/login", json={"email": cust_email, "password": "CustPass123!"}, timeout=60).status_code == 401)
        check("Suspended user's token stops working", httpx.get(f"{base}/auth/me", headers=ch, timeout=60).status_code == 401)
        pub = httpx.post(f"{base}/public/chat", json={"token": embed, "message": "hi"}, timeout=60)
        check("Suspended owner's widget answers 503", pub.status_code == 503 and "temporarily unavailable" in pub.json()["detail"].lower())
        httpx.post(f"{base}{ADMIN}/users/{cust_id}/reactivate", headers=sh, timeout=60)
        check("Reactivated user can log in again", httpx.post(f"{base}/auth/login", json={"email": cust_email, "password": "CustPass123!"}, timeout=60).status_code == 200)

        # ── 10. Plans, trials, payments, audit rows ───────────────────────────
        httpx.post(f"{base}{ADMIN}/subscriptions/{cust_id}/plan", json={"plan": "standard", "reason": "upgrade"}, headers=sh, timeout=60)
        me_info = httpx.post(f"{base}/auth/login", json={"email": cust_email, "password": "CustPass123!"}, timeout=60).json()
        me = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {me_info['access_token']}"}, timeout=60).json()
        check("Plan change is visible in /auth/me", me["plan"]["base"] == "standard")
        pay = httpx.post(f"{base}{ADMIN}/payments/{cust_id}", json={"amount_tzs": 7800, "method": "mpesa", "reference": "T1"}, headers=sh, timeout=60)
        check("Manual payment recorded", pay.status_code == 200)
        payments = httpx.get(f"{base}{ADMIN}/payments", headers=sh, timeout=60).json()
        check("Payment appears in the ledger", any(p["reference"] == "T1" for p in payments["items"]))
        audit = httpx.get(f"{base}{ADMIN}/audit", headers=sh, timeout=60).json()
        actions = {item["action"] for item in audit["items"]}
        check("Audit rows exist for plan and payment", {"billing.plan_change", "billing.payment_recorded"} <= actions)

        # ── 11. Audit immutability ────────────────────────────────────────────
        with sqlite3.connect(db_path) as conn:
            probe_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO audit_log (id, ts, actor_id, actor_email, action, "
                "summary) VALUES (?, ?, NULL, NULL, 'probe', 'probe')",
                (probe_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            try:
                conn.execute("DELETE FROM audit_log WHERE id = ?", (probe_id,))
                conn.commit()
                immutable_delete = False
            except sqlite3.Error:
                immutable_delete = True
            try:
                conn.execute("UPDATE audit_log SET summary = 'x' WHERE id = ?", (probe_id,))
                conn.commit()
                immutable_update = False
            except sqlite3.Error:
                immutable_update = True
        check("Audit log rejects UPDATE and DELETE at the DB level", immutable_delete and immutable_update)

        # ── 12. Secret hygiene ────────────────────────────────────────────────
        leaked = []
        for method, path in [(m, p) for m, p in ops if m == "GET"]:
            target = fill(path)
            response = httpx.get(base + target, headers=sh, timeout=60)
            if response.status_code == 200:
                try:
                    payload = json.dumps(response.json(), default=str)
                except Exception:
                    continue
                for pattern in ("$2b$", "password_hash", "token_hash", "key_hash", "totp_secret", "sk-botbase-"):
                    if pattern in payload:
                        leaked.append((path, pattern))
        check("No secret fields or hash patterns in admin GET responses", not leaked, str(leaked[:5]))

        # ── 14. Deletion cascade ──────────────────────────────────────────────
        victim_email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
        victim = httpx.post(f"{base}/auth/register", json={"email": victim_email, "password": "VictimPass123!"}, timeout=60).json()
        vh = {"Authorization": f"Bearer {victim['access_token']}"}
        vws = httpx.post(f"{base}/workspaces", json={"name": "v"}, headers=vh, timeout=60).json()
        vagent = httpx.post(f"{base}/workspaces/{vws['id']}/agents", json={"name": "va", "system_prompt": "x and more words"}, headers=vh, timeout=60).json()
        httpx.post(f"{base}/workspaces/{vws['id']}/agents/{vagent['id']}/tokens", json={"label": "v"}, headers=vh, timeout=60)
        users_page = httpx.get(f"{base}{ADMIN}/users", params={"search": victim_email}, headers=sh, timeout=60).json()
        victim_id = users_page["items"][0]["id"]
        delete = httpx.request(
            "DELETE", f"{base}{ADMIN}/users/{victim_id}",
            json={"email_confirmation": victim_email, "reauth_password": FOUNDER_PASSWORD},
            headers=sh, timeout=120,
        )
        check("Permanent deletion succeeds", delete.status_code == 200, delete.text[:200])
        with sqlite3.connect(db_path) as conn:
            orphans = []
            for table, column, value in (
                ("workspaces", "id", vws["id"]),
                ("agents", "workspace_id", vws["id"]),
                ("agent_embed_tokens", "agent_id", vagent["id"]),
                ("users", "id", victim_id),
            ):
                count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (value,)).fetchone()[0]
                if count:
                    orphans.append((table, count))
        check("Deletion cascade leaves zero orphans", not orphans, str(orphans))

        # ── 15. Platform controls ─────────────────────────────────────────────
        httpx.put(f"{base}{ADMIN}/platform/settings", json={"signups_open": False, "reauth_password": FOUNDER_PASSWORD}, headers=sh, timeout=60)
        blocked = httpx.post(f"{base}/auth/register", json={"email": f"no-{uuid.uuid4().hex[:6]}@example.com", "password": "BlockedPass123!"}, timeout=60)
        check("Closing signups blocks registration with a clear message", blocked.status_code == 403 and "closed" in blocked.json()["detail"].lower())
        httpx.put(f"{base}{ADMIN}/platform/settings", json={"emergency_off": True, "reauth_password": FOUNDER_PASSWORD}, headers=sh, timeout=60)
        emergency = httpx.post(f"{base}/public/chat", json={"token": "bogus", "message": "hi"}, timeout=60)
        check("Emergency switch answers public chat with friendly 503", emergency.status_code == 503 and "temporarily unavailable" in emergency.json()["detail"].lower())
        dev_health_after = httpx.get(f"{base}/api/v1/health", timeout=60)
        check("Developer health stays up (informational)", dev_health_after.status_code == 200)
        httpx.put(f"{base}{ADMIN}/platform/settings", json={"signups_open": True, "emergency_off": False, "reauth_password": FOUNDER_PASSWORD}, headers=sh, timeout=60)
        reopened = httpx.post(f"{base}/auth/register", json={"email": f"yes-{uuid.uuid4().hex[:6]}@example.com", "password": "OpenPass123!"}, timeout=60)
        check("Reopening signups restores registration", reopened.status_code == 201)
        audit_after = httpx.get(f"{base}{ADMIN}/audit", headers=sh, timeout=60).json()
        check("Every platform change was audited", sum(1 for a in audit_after["items"] if a["action"] == "platform.settings") >= 3)

        # ── 16. TOTP flow ─────────────────────────────────────────────────────
        setup = httpx.post(f"{base}{ADMIN}/my-account/totp/setup", json={"reauth_password": FOUNDER_PASSWORD}, headers=sh, timeout=60)
        check("TOTP setup returns a secret and QR", setup.status_code == 200 and "qr_data_uri" in setup.json())
        secret2 = setup.json()["secret"]
        verify = httpx.post(f"{base}{ADMIN}/my-account/totp/verify", json={"code": totp.code_at(secret2, int(time.time()))}, headers=sh, timeout=60)
        check("TOTP enabled with recovery codes", verify.status_code == 200 and len(verify.json()["recovery_codes"]) == 10)
        recovery = verify.json()["recovery_codes"][0]
        challenge = httpx.post(f"{base}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD}, timeout=60)
        check("Login now returns a TOTP challenge", challenge.status_code == 200 and challenge.json()["token_type"] == "totp")
        wrong = httpx.post(f"{base}/auth/login/totp", json={"totp_token": challenge.json()["totp_token"], "code": "000000"}, timeout=60)
        check("Wrong TOTP code is rejected", wrong.status_code == 401)
        good = httpx.post(f"{base}/auth/login/totp", json={"totp_token": challenge.json()["totp_token"], "code": totp.code_at(secret2, int(time.time()))}, timeout=60)
        check("Correct TOTP code signs in", good.status_code == 200)
        challenge2 = httpx.post(f"{base}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD}, timeout=60)
        rec_once = httpx.post(f"{base}/auth/login/totp", json={"totp_token": challenge2.json()["totp_token"], "code": recovery}, timeout=60)
        challenge3 = httpx.post(f"{base}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD}, timeout=60)
        rec_twice = httpx.post(f"{base}/auth/login/totp", json={"totp_token": challenge3.json()["totp_token"], "code": recovery}, timeout=60)
        check("Recovery code works once then is rejected", rec_once.status_code == 200 and rec_twice.status_code == 401)

        # ── 17. Performance: 20k usage rows, thousands of users ───────────────
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO usage_events (id, workspace_id, kind, quantity, created_at, "
                "channel, model, status, latency_ms) VALUES (?, ?, 'chat', 1, ?, 'widget', 'm', 'ok', 40)",
                [(str(uuid.uuid4()), ws["id"], now_iso) for _ in range(20000)],
            )
            conn.executemany(
                "INSERT INTO users (id, email, hashed_password, is_active, created_at, plan) "
                "VALUES (?, ?, 'x', 1, ?, 'free')",
                [(str(uuid.uuid4()), f"seed-{i}@example.com", now_iso) for i in range(3000)],
            )
            conn.commit()
        overview_start = time.perf_counter()
        overview_perf = httpx.get(f"{base}{ADMIN}/overview", headers=sh, timeout=60)
        overview_elapsed = time.perf_counter() - overview_start
        usage_start = time.perf_counter()
        usage_perf = httpx.get(f"{base}{ADMIN}/usage/summary", headers=sh, timeout=60)
        usage_elapsed = time.perf_counter() - usage_start
        check(
            "Overview under a second with 20k+ rows",
            overview_perf.status_code == 200 and overview_elapsed < 1.0,
            f"{overview_elapsed * 1000:.0f}ms",
        )
        check(
            "Usage summary under a second with 20k+ rows",
            usage_perf.status_code == 200 and usage_elapsed < 1.0,
            f"{usage_elapsed * 1000:.0f}ms",
        )

    except Exception as exc:  # pragma: no cover
        detail = f"{type(exc).__name__}: {exc}"
        try:
            tail = log_path.read_text(errors="ignore")[-500:]
            if tail.strip():
                detail += f" | log tail: {tail}"
        except (NameError, FileNotFoundError):
            pass
        check("Script completed without unexpected errors", False, detail)
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=20)
            except Exception:
                server.kill()

    print()
    failed = [item for item in results if not item[1]]
    print(f"RESULT: {len(results) - len(failed)} passed, {len(failed)} failed, {len(results)} total")
    for name, _, detail in failed:
        print(f"  FAIL {name} — {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
