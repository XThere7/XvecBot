#!/usr/bin/env python3
"""
verify_welcome_email.py
End-to-end verification of the automated welcome email against a live server.

Run from the repository root inside the backend environment (the app's
dependencies must be importable), for example:

    docker exec -w /app/backend botbase-api-5434 \
        env PYTHONPATH=/app/backend python /app/scripts/verify_welcome_email.py

The script:
  * starts its own throwaway uvicorn server on a free port with
    EMAIL_BACKEND=file and a clean outbox (never the developer's real DB),
  * registers, logs in, re-registers, and inspects the produced .eml files,
  * restarts the server with a failing SMTP configuration (closed port) and
    proves registration still succeeds,
  * prints a PASS/FAIL report and exits non-zero on any failure.

No real mail can be sent: the file backend writes to the outbox, and the SMTP
phase points at a closed local port.
"""
from __future__ import annotations

import email.parser
import email.policy
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
from pathlib import Path

import httpx

from app.core.plan import TRIAL_DAYS

_SCRIPT_DIR = Path(__file__).resolve().parent
# Resolve the backend package root whether the script runs from the repo
# checkout (repo/scripts/... -> repo/backend) or from the app container
# (mounted at /app/backend).
_BACKEND_CANDIDATES = [
    Path("/app/backend"),
    _SCRIPT_DIR.parent / "backend",
]
ROOT = next(
    (candidate for candidate in _BACKEND_CANDIDATES if (candidate / "app" / "main.py").exists()),
    _SCRIPT_DIR.parent / "backend",
)
FRONTEND_URL = "http://localhost:3000"
DOCS_URL = "http://localhost:3000/docs"
FROM_ADDRESS = "botbasex7@gmail.com"
FROM_NAME = "BotBase"
SUPPORT = "botbasex7@gmail.com"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {name}" + (f" — {detail}" if detail else ""))


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
        "EMAIL_FROM_ADDRESS": FROM_ADDRESS,
        "EMAIL_FROM_NAME": FROM_NAME,
        "EMAIL_REPLY_TO": SUPPORT,
        "SUPPORT_EMAIL": SUPPORT,
        "FRONTEND_URL": FRONTEND_URL,
        "DOCS_URL": DOCS_URL,
        "DEBUG": "true",
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(24),
        "DEFAULT_WORKSPACE_PLAN": "free",
        "OPENROUTER_API_KEY": "",
        "LOG_LEVEL": "INFO",
    }


def start_server(tmp: Path, extra_env: dict[str, str] | None = None) -> tuple[subprocess.Popen, int, Path]:
    port = free_port()
    # Inherit the ambient environment (HF caches, PATH) and overlay the
    # throwaway config on top.
    env = {**os.environ, **base_env(tmp)}
    env["PYTHONPATH"] = str(ROOT)
    if extra_env:
        env.update(extra_env)
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
            response = httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=5)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("server did not become healthy in time")


def outbox_files(tmp: Path) -> list[Path]:
    return sorted((tmp / "outbox").glob("*.eml"))


def read_eml(path: Path):
    return email.parser.Parser(policy=email.policy.default).parsestr(
        path.read_text(encoding="utf-8", errors="replace")
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="botbase-email-verify-"))
    (tmp / "outbox").mkdir(exist_ok=True)
    servers: list[subprocess.Popen] = []
    try:
        print(f"Verification workspace: {tmp}")
        # ── Phase 1: file backend ────────────────────────────────────────────
        server, port, log_path = start_server(tmp)
        servers.append(server)
        wait_health(port)
        base = f"http://127.0.0.1:{port}"

        # Seed a pre-existing account created before this feature existed.
        legacy_email = f"legacy-{uuid.uuid4().hex[:8]}@example.com"
        db_path = tmp / "rag.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users (id, email, hashed_password, is_active, created_at, "
                "plan, trial_ends_at, welcome_email_sent_at) "
                "VALUES (?, ?, ?, 1, ?, 'free', NULL, NULL)",
                (str(uuid.uuid4()), legacy_email, "not-a-hash", "2026-01-01T00:00:00+00:00"),
            )
            conn.commit()

        new_email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
        password = "VerifyPass123!"
        response = httpx.post(
            f"{base}/auth/register", json={"email": new_email, "password": password}, timeout=30
        )
        check("Registration returns the unchanged 201 contract", response.status_code == 201, f"status={response.status_code}")
        body = response.json()
        check("Registration response keeps access_token and user_id", bool(body.get("access_token")) and bool(body.get("user_id")))

        # Background task lands within a few seconds; response is not blocked.
        deadline = time.time() + 15
        files: list[Path] = []
        while time.time() < deadline and not files:
            files = outbox_files(tmp)
            if not files:
                time.sleep(0.25)
        check("Exactly one .eml appears for the new address", len(files) == 1, f"files={len(files)}")
        if files:
            eml_path = files[0]
            message = read_eml(eml_path)
            check(
                "Subject matches exactly (emoji included)",
                str(message["Subject"]) == f"Welcome to {FROM_NAME} – Your AI Journey Starts Here! 🚀",
                str(message["Subject"]),
            )
            check("From header comes from config", message["From"] == f"{FROM_NAME} <{FROM_ADDRESS}>", str(message["From"]))
            check("Reply-To header comes from config", message["Reply-To"] == SUPPORT, str(message["Reply-To"]))
            check("Message has both plain and HTML parts", message.is_multipart() and message.get_body(preferencelist=("plain",)) is not None and message.get_body(preferencelist=("html",)) is not None)
            plain = message.get_body(preferencelist=("plain",)).get_content()
            html = message.get_body(preferencelist=("html",)).get_content()
            check("Message-ID and Date headers are present", bool(message["Message-ID"]) and bool(message["Date"]))

            check("HTML has no unrendered placeholders or Nones", not re.search(r"\{\{|\{first_name\}|\{BRAND\}|None", html))
            check("Docs link equals the configured URL", DOCS_URL in html)
            check("Dashboard link equals the configured URL", f"{FRONTEND_URL}/dashboard" in html)
            hrefs = re.findall(r'href="([^"]+)"', html)
            check("Every HTML link also appears in the text part", all(href in plain for href in hrefs), f"links={hrefs}")
            check("Trial sentence present with the real duration", f"{TRIAL_DAYS}-day free trial" in html and f"{TRIAL_DAYS}-day free trial" in plain, f"TRIAL_DAYS={TRIAL_DAYS}")
            check("Container max-width is 600px", "max-width: 600px" in html)
            check("No fixed width above 600px", all(int(w) <= 600 for w in re.findall(r"width:\s*(\d+)px", html)))
            check("Viewport meta is present", 'name="viewport"' in html)
            check("Buttons carry text fallbacks", "Explore BotBase Documentation" in html and "Open My BotBase Dashboard" in html)
            check("Hidden preheader is present", "display: none" in html and "mso-hide: all" in html)
            # Keep a host-visible copy of the rendered message for screenshot review.
            preview_dir = Path("/app/data/verify_outbox")
            if preview_dir.parent.exists():
                preview_dir.mkdir(exist_ok=True)
                (preview_dir / "welcome.html").write_text(html, encoding="utf-8")
                (preview_dir / "welcome.eml").write_bytes(eml_path.read_bytes())

        # ── Idempotency ──────────────────────────────────────────────────────
        for _ in range(3):
            login = httpx.post(f"{base}/auth/login", json={"email": new_email, "password": password}, timeout=30)
            check("Login succeeds repeatedly without sending mail", login.status_code == 200, f"status={login.status_code}")
        duplicate = httpx.post(f"{base}/auth/register", json={"email": new_email, "password": password}, timeout=30)
        check("Duplicate registration is refused", duplicate.status_code == 400, f"status={duplicate.status_code}")
        time.sleep(1.0)
        files_after = outbox_files(tmp)
        check("Exactly one email despite logins and re-registration", len(files_after) == 1, f"files={len(files_after)}")
        check(
            "Pre-existing accounts received nothing",
            all(str(message["To"]) != legacy_email for message in (read_eml(path) for path in files_after)),
            f"legacy={legacy_email}",
        )

        # ── Phase 2: failing SMTP backend ────────────────────────────────────
        server.terminate()
        server.wait(timeout=20)
        servers.clear()
        closed_port = free_port()
        fail_env = {
            "EMAIL_BACKEND": "smtp",
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": str(closed_port),
            "SMTP_USERNAME": FROM_ADDRESS,
            "SMTP_PASSWORD": "TestMailPassword123!",
            "SMTP_SECURITY": "starttls",
        }
        server2, port2, log2 = start_server(tmp, fail_env)
        servers.append(server2)
        wait_health(port2)
        base2 = f"http://127.0.0.1:{port2}"
        failing_email = f"fail-{uuid.uuid4().hex[:8]}@example.com"
        fail_password = "VerifyPass123!"
        response = httpx.post(f"{base2}/auth/register", json={"email": failing_email, "password": fail_password}, timeout=30)
        check("Registration still succeeds when mail fails", response.status_code == 201, f"status={response.status_code}")
        login = httpx.post(f"{base2}/auth/login", json={"email": failing_email, "password": fail_password}, timeout=30)
        check("The user can still sign in", login.status_code == 200, f"status={login.status_code}")
        time.sleep(2.0)
        check("No extra email appears in the outbox", len(outbox_files(tmp)) == 1, f"files={len(outbox_files(tmp))}")
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT welcome_email_sent_at FROM users WHERE email = ?", (failing_email,)
            ).fetchone()
        check("welcome_email_sent_at stays NULL after a failed send", row is not None and row[0] is None)
        logs = log2.read_text(errors="ignore") + log_path.read_text(errors="ignore")
        check("Logs contain no body text, address or SMTP password", ("AI Journey" not in logs) and (failing_email not in logs) and ("TestMailPassword123!" not in logs))

    except Exception as exc:  # pragma: no cover
        detail = f"{type(exc).__name__}: {exc}"
        try:
            tail = log_path.read_text(errors="ignore")[-600:]
            if tail.strip():
                detail += f" | server log tail: {tail}"
        except NameError:
            pass
        check("Script completed without unexpected errors", False, detail)
    finally:
        for server in servers:
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
    from app.core.plan import TRIAL_DAYS

    raise SystemExit(main())
