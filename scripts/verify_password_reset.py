#!/usr/bin/env python3
"""
verify_password_reset.py
End-to-end verification of self-service password recovery against a live server.

Run from the repository root inside the backend environment (app dependencies
must be importable), for example:

    docker exec -w /app/backend botbase-api-5434 \
        env PYTHONPATH=/app/backend python /app/scripts/verify_password_reset.py

The script starts its own throwaway uvicorn server on a free port with
EMAIL_BACKEND=file and a clean outbox (never the developer's real DB), then
exercises: neutral forgot-password responses, hashed single-use tokens,
30-minute expiry, atomic consumption, session invalidation, rate limits,
cross-user binding, email quality and a full log audit for token/password
leakage.

No real mail can be sent (file backend only).
"""
from __future__ import annotations

import asyncio
import email.parser
import email.policy
import hashlib
import os
import re
import secrets
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

from app.core.plan import TRIAL_DAYS  # noqa: F401 — imports the app package
from app.services.password_reset_service import FORGOT_RESPONSE

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_CANDIDATES = [Path("/app/backend"), _SCRIPT_DIR.parent / "backend"]
ROOT = next(
    (candidate for candidate in _BACKEND_CANDIDATES if (candidate / "app" / "main.py").exists()),
    _SCRIPT_DIR.parent / "backend",
)

FRONTEND_URL = "http://localhost:3000"
GENERIC_INVALID = "This reset link is invalid or has expired."
EMAIL_LIMIT = "3"
IP_LIMIT = "100"

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
        "PASSWORD_RESET_TOKEN_TTL_MINUTES": "30",
        "PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR": EMAIL_LIMIT,
        "PASSWORD_RESET_MAX_PER_IP_PER_HOUR": IP_LIMIT,
        "DEBUG": "true",
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(24),
        "DEFAULT_WORKSPACE_PLAN": "free",
        "OPENROUTER_API_KEY": "",
        "LOG_LEVEL": "INFO",
    }


def start_server(tmp: Path) -> tuple[subprocess.Popen, int, Path]:
    port = free_port()
    # Inherit the ambient environment (HF caches, PATH) and overlay the
    # throwaway config on top.
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


def outbox_files(tmp: Path) -> list[Path]:
    return sorted((tmp / "outbox").glob("*.eml"), key=os_path_mtime)


def os_path_mtime(p: Path) -> float:
    return p.stat().st_mtime


def read_eml(path: Path):
    return email.parser.Parser(policy=email.policy.default).parsestr(
        path.read_text(encoding="utf-8", errors="replace")
    )


def wait_for_mails(tmp: Path, addr: str, subject_prefix: str, count: int, timeout: float = 15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []
        for path in outbox_files(tmp):
            message = read_eml(path)
            if (message["To"] or "").lower() == addr.lower() and str(
                message["Subject"]
            ).startswith(subject_prefix):
                found.append(message)
        if len(found) >= count:
            return found
        time.sleep(0.25)
    found = []
    for path in outbox_files(tmp):
        message = read_eml(path)
        if (message["To"] or "").lower() == addr.lower() and str(message["Subject"]).startswith(subject_prefix):
            found.append(message)
    return found


def token_from(message) -> str:
    plain = message.get_body(preferencelist=("plain",)).get_content()
    match = re.search(r"token=([A-Za-z0-9_\-]+)", plain)
    assert match, f"no reset link in email body: {plain[:200]!r}"
    return match.group(1)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="botbase-reset-verify-"))
    (tmp / "outbox").mkdir(exist_ok=True)
    server: subprocess.Popen | None = None
    try:
        print(f"Verification workspace: {tmp}")
        server, port, log_path = start_server(tmp)
        wait_health(port)
        base = f"http://127.0.0.1:{port}"

        def register(password: str = "OldPass123!") -> str:
            email = f"{uuid.uuid4().hex[:10]}@example.com"
            response = httpx.post(
                f"{base}/auth/register",
                json={"email": email, "password": password},
                timeout=60,
            )
            assert response.status_code == 201, response.text
            return email

        def forgot(email: str):
            return httpx.post(f"{base}/auth/forgot-password", json={"email": email}, timeout=60)

        # ── 1. Neutral response + one reset email ─────────────────────────────
        email_a = register()
        known_response = forgot(email_a)
        check(
            "Forgot password returns the neutral 200 body",
            known_response.status_code == 200 and known_response.json() == FORGOT_RESPONSE,
            f"status={known_response.status_code}",
        )
        reset_mails = wait_for_mails(tmp, email_a, "Reset your", 1)
        check("One reset email arrives for the address", len(reset_mails) == 1, f"mails={len(reset_mails)}")
        reset_url = None
        if reset_mails:
            html = reset_mails[0].get_body(preferencelist=("html",)).get_content()
            reset_url = re.search(r'href="([^"]*reset-password\?token=[^"]+)"', html)
            check(
                "Reset link points at the configured FRONTEND_URL",
                reset_url is not None and reset_url.group(1).startswith(FRONTEND_URL),
                f"{FRONTEND_URL}/reset-password?token=…" if reset_url else "no link",
            )
            token_a = token_from(reset_mails[0])

        # ── 2. Unknown address: identical body, no mail, similar timing ───────
        unknown = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
        unknown_response = forgot(unknown)
        check(
            "Unknown address returns the identical status and body",
            unknown_response.status_code == known_response.status_code
            and unknown_response.json() == known_response.json(),
        )
        time.sleep(1.0)
        check(
            "No email produced for the unknown address",
            len(wait_for_mails(tmp, unknown, "Reset your", 1, timeout=2)) == 0,
        )
        timing_email = register()
        known_times, unknown_times = [], []
        for _ in range(3):
            start = time.perf_counter()
            forgot(timing_email)
            known_times.append(time.perf_counter() - start)
            start = time.perf_counter()
            forgot(unknown)
            unknown_times.append(time.perf_counter() - start)
        known_avg, unknown_avg = statistics.mean(known_times), statistics.mean(unknown_times)
        check(
            "Response times are not distinguishable by account existence",
            abs(known_avg - unknown_avg) < 1.0,
            f"known={known_avg * 1000:.1f}ms unknown={unknown_avg * 1000:.1f}ms",
        )

        # ── 3. Malformed email: same body, no mail ────────────────────────────
        malformed = forgot("not-an-email-address")
        check(
            "Malformed address returns the identical neutral body",
            malformed.status_code == 200 and malformed.json() == FORGOT_RESPONSE,
            f"status={malformed.status_code}",
        )

        # ── 4. DB stores only the hash; expiry is exactly the configured TTL ──
        db_path = tmp / "rag.db"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT token_hash, created_at, expires_at, used_at FROM password_reset_tokens "
                "WHERE token_hash = ?",
                (hashlib.sha256(token_a.encode()).hexdigest(),),
            ).fetchone()
        check("Raw token is absent from the database (hash only)", row is not None and token_a not in row[0])
        if row:
            token_hash, created_at, expires_at, used_at = row
            check(
                "Stored value is the SHA-256 of the token",
                token_hash == hashlib.sha256(token_a.encode()).hexdigest(),
            )
            from datetime import datetime

            delta_minutes = (
                datetime.fromisoformat(expires_at) - datetime.fromisoformat(created_at)
            ).total_seconds() / 60
            check("Expiry is 30 minutes from creation", 29 <= delta_minutes <= 31, f"{delta_minutes:.2f}min")
            check("Token is unused", used_at is None)

        # ── 5. Reset succeeds; new password works; old fails ──────────────────
        reset = httpx.post(
            f"{base}/auth/reset-password",
            json={"token": token_a, "new_password": "NewPass123!", "confirm_password": "NewPass123!"},
            timeout=60,
        )
        check("Valid token resets the password", reset.status_code == 200, f"status={reset.status_code}")
        login_new = httpx.post(f"{base}/auth/login", json={"email": email_a, "password": "NewPass123!"}, timeout=60)
        check("New password signs in", login_new.status_code == 200)
        login_old = httpx.post(f"{base}/auth/login", json={"email": email_a, "password": "OldPass123!"}, timeout=60)
        check("Old password is rejected", login_old.status_code == 401)
        changed_mails = wait_for_mails(tmp, email_a, "Your BotBase password was changed", 1)
        check("Password-changed notice is sent after the reset", len(changed_mails) == 1, f"mails={len(changed_mails)}")

        # ── 6. Token reuse is rejected ────────────────────────────────────────
        reuse = httpx.post(
            f"{base}/auth/reset-password",
            json={"token": token_a, "new_password": "AnotherPass123!"},
            timeout=60,
        )
        check(
            "Reusing the token returns the generic error",
            reuse.status_code == 400 and reuse.json().get("detail") == GENERIC_INVALID,
            f"status={reuse.status_code}",
        )

        # ── 7. A newer request invalidates the earlier link ───────────────────
        email_b = register()
        forgot(email_b)
        first = token_from(wait_for_mails(tmp, email_b, "Reset your", 1)[0])
        forgot(email_b)
        second_mails = wait_for_mails(tmp, email_b, "Reset your", 2)
        check("Two reset emails for two requests", len(second_mails) == 2)
        second = token_from(second_mails[1])
        stale = httpx.post(
            f"{base}/auth/reset-password", json={"token": first, "new_password": "NewPass123!"}, timeout=60
        )
        check(
            "The first link no longer works",
            stale.status_code == 400 and stale.json().get("detail") == GENERIC_INVALID,
            f"status={stale.status_code}",
        )
        fresh = httpx.post(
            f"{base}/auth/reset-password", json={"token": second, "new_password": "NewPass123!"}, timeout=60
        )
        check("The second link works", fresh.status_code == 200, f"status={fresh.status_code}")

        # ── 8. Expired token is rejected ──────────────────────────────────────
        email_c = register()
        forgot(email_c)
        token_c = token_from(wait_for_mails(tmp, email_c, "Reset your", 1)[0])
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
                (past, hashlib.sha256(token_c.encode()).hexdigest()),
            )
            conn.commit()
        expired = httpx.post(
            f"{base}/auth/reset-password", json={"token": token_c, "new_password": "NewPass123!"}, timeout=60
        )
        check(
            "Expired token is rejected with the generic error",
            expired.status_code == 400 and expired.json().get("detail") == GENERIC_INVALID,
            f"status={expired.status_code}",
        )

        # ── 9. Weak password / mismatch never consume the token ───────────────
        email_d = register()
        forgot(email_d)
        token_d = token_from(wait_for_mails(tmp, email_d, "Reset your", 1)[0])
        weak = httpx.post(
            f"{base}/auth/reset-password", json={"token": token_d, "new_password": "short"}, timeout=60
        )
        check("Weak password is rejected", weak.status_code == 422, f"status={weak.status_code}")
        mismatch = httpx.post(
            f"{base}/auth/reset-password",
            json={"token": token_d, "new_password": "NewPass123!", "confirm_password": "Different123!"},
            timeout=60,
        )
        check("Mismatched confirmation is rejected", mismatch.status_code == 400, f"status={mismatch.status_code}")
        still_ok = httpx.post(
            f"{base}/auth/reset-password",
            json={"token": token_d, "new_password": "NewPass123!", "confirm_password": "NewPass123!"},
            timeout=60,
        )
        check("Token survived both rejections", still_ok.status_code == 200, f"status={still_ok.status_code}")

        # ── 10. Concurrency: exactly one wins ──────────────────────────────────
        email_e = register()
        forgot(email_e)
        token_e = token_from(wait_for_mails(tmp, email_e, "Reset your", 1)[0])

        async def concurrent():
            async with httpx.AsyncClient(timeout=60) as client:
                first_call = client.post(
                    f"{base}/auth/reset-password",
                    json={"token": token_e, "new_password": "NewPass123!"},
                )
                second_call = client.post(
                    f"{base}/auth/reset-password",
                    json={"token": token_e, "new_password": "NewPass123!"},
                )
                return await asyncio.gather(first_call, second_call)

        first_result, second_result = asyncio.run(concurrent())
        statuses = sorted([first_result.status_code, second_result.status_code])
        check("Two simultaneous uses: exactly one succeeds", statuses == [200, 400], str(statuses))

        # ── 11. Session invalidation ───────────────────────────────────────────
        email_f = register()
        pre_login = httpx.post(f"{base}/auth/login", json={"email": email_f, "password": "OldPass123!"}, timeout=60)
        old_token = pre_login.json()["access_token"]
        me_before = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {old_token}"}, timeout=60)
        check("Old session works before the reset", me_before.status_code == 200)
        forgot(email_f)
        token_f = token_from(wait_for_mails(tmp, email_f, "Reset your", 1)[0])
        httpx.post(
            f"{base}/auth/reset-password", json={"token": token_f, "new_password": "NewPass123!"}, timeout=60
        )
        me_after = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {old_token}"}, timeout=60)
        check("Old session is rejected after the reset", me_after.status_code == 401, f"status={me_after.status_code}")
        other_email = register()
        other_login = httpx.post(
            f"{base}/auth/login", json={"email": other_email, "password": "OldPass123!"}, timeout=60
        )
        me_other = httpx.get(
            f"{base}/auth/me",
            headers={"Authorization": f"Bearer {other_login.json()['access_token']}"},
            timeout=60,
        )
        check("A user who did not reset keeps their session", me_other.status_code == 200)

        # ── 12. Rate limiting ──────────────────────────────────────────────────
        email_g = register()
        statuses_g = [forgot(email_g).status_code for _ in range(int(EMAIL_LIMIT) + 1)]
        check(
            "The per-email hourly limit returns 429 with the same neutral body",
            statuses_g[: int(EMAIL_LIMIT)] == [200] * int(EMAIL_LIMIT)
            and statuses_g[-1] == 429
            and forgot(email_g).json() == FORGOT_RESPONSE,
            f"statuses={statuses_g}",
        )
        email_h = register()
        check(
            "A different address is not blocked by the first one's limit",
            forgot(email_h).status_code == 200,
        )

        # ── 13. A token only ever changes its own account ──────────────────────
        email_i = register()
        email_j = register()
        forgot(email_i)
        token_i = token_from(wait_for_mails(tmp, email_i, "Reset your", 1)[0])
        httpx.post(
            f"{base}/auth/reset-password", json={"token": token_i, "new_password": "NewPass123!"}, timeout=60
        )
        j_login = httpx.post(f"{base}/auth/login", json={"email": email_j, "password": "OldPass123!"}, timeout=60)
        check("Another account's password is untouched", j_login.status_code == 200)

        # ── 14. Log audit ──────────────────────────────────────────────────────
        logs = log_path.read_text(errors="ignore")
        raw_tokens = [token_a, token_c, token_d, token_e, token_f, token_i]
        leaked_tokens = [t for t in raw_tokens if t and t in logs]
        check("No raw token appears in the server log", not leaked_tokens)
        check("No reset URL appears in the server log", "reset-password?token=" not in logs)
        check("No plaintext test password appears in the server log", "OldPass123!" not in logs and "NewPass123!" not in logs)

        # ── 15. Email quality ─────────────────────────────────────────────────
        email_k = register()
        forgot(email_k)
        quality_mail = wait_for_mails(tmp, email_k, "Reset your", 1)[0]
        plain = quality_mail.get_body(preferencelist=("plain",)).get_content()
        html = quality_mail.get_body(preferencelist=("html",)).get_content()
        check("Reset email has text and HTML parts", bool(plain) and bool(html))
        hrefs = re.findall(r'href="([^"]+)"', html)
        reset_hrefs = [h for h in hrefs if "reset-password?token=" in h]
        check("The same reset link appears in both parts", all(h in plain for h in reset_hrefs), f"links={len(reset_hrefs)}")
        check("The 30-minute expiry notice is present", "30 minutes" in plain and "30 minutes" in html)
        check("'Password has not changed' notice is present", "has not changed" in plain.lower())
        check("No unrendered placeholders", not re.search(r"\{\{|\{BRAND\}|None", html + plain))
        check("No password material in the mail", "OldPass123!" not in plain and "OldPass123!" not in html)

    except Exception as exc:  # pragma: no cover
        detail = f"{type(exc).__name__}: {exc}"
        try:
            tail = log_path.read_text(errors="ignore")[-600:]
            if tail.strip():
                detail += f" | server log tail: {tail}"
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
