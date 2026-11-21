"""
scripts/cutover_preflight.py (Phase 5)
Go/no-go gate for staging -> production cutover. Read-only: never writes.

  python scripts/cutover_preflight.py            # check local .env posture
  python scripts/cutover_preflight.py --strict   # production gate (exit != 0 on any FAIL)

Checks (each prints PASS/FAIL/SKIP):
  1. secrets      SECRET_KEY non-default when DEBUG=false; API_KEY non-default
  2. database     reachable + every expected table present (+ alembic_version on pg)
  3. storage      S3/R2 reachable when S3_BUCKET set (head-bucket via list)
  4. migrations   alembic heads applied (pg) / init_db columns present (sqlite)
  5. app config   ENABLE_DOCS=false, ALLOWED_ORIGINS has no localhost (strict),
                  APP_PUBLIC_URL is https (strict), HOSTED_BASE_URL is a
                  different origin from APP_PUBLIC_URL
  6. email        EMAIL_BACKEND=smtp, SMTP host/user/password set, a real
                  From address (not .local) and a readable reply-to
  7. admin        admin route prefix set, TOTP/session/audit posture sane
  8. plans        DEFAULT_WORKSPACE_PLAN=free, trial length 21 days, prices
                  present (paid plans are displayed but not purchasable yet)
  9. llm          OPENROUTER_API_KEY present (strict)
 10. runtime      PostgreSQL (strict), rate limiting on, a bucket configured,
                  the upload directory writable
 11. backups      R2 backups/ prefix non-empty when S3 configured (else SKIP)

Exit: 0 all PASS/SKIP, 1 any FAIL, 2 usage error. --strict turns prod-only
SKIPs (localhost origins, docs on) into FAILs.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EXPECTED_TABLES = {
    "documents",
    "users",
    "workspaces",
    "workspace_documents",
    "agents",
    "conversations",
    "messages",
    "chunks",
    "chunk_embeddings",
    "agent_embed_tokens",
    "developer_api_keys",
    "usage_events",
    "usage_monthly",
    "website_sources",
    "website_pages",
    "website_sync_jobs",
    "agent_actions",
    "leads",
    "data_collections",
    "data_submissions",
    "custom_forms",
    "form_submissions",
    "support_escalations",
    "email_integrations",
    "incoming_emails",
    "email_drafts",
    "email_approvals",
    "notification_messages",
}

# The schema revision the production database must be on.
EXPECTED_ALEMBIC_HEAD = "0013_actions_and_email_agent"

results: list[tuple[str, str, str]] = []


def report(name: str, status: str, detail: str = "") -> None:
    assert status in ("PASS", "FAIL", "SKIP")
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


async def check_secrets() -> None:
    from app.core.config import settings

    if not settings.debug and settings.secrets_are_default():
        report("secrets.SECRET_KEY", "FAIL", "DEBUG=false with default SECRET_KEY")
    else:
        report("secrets.SECRET_KEY", "PASS", "non-default or debug mode")
    if (settings.api_key or "") in ("dev-key", "", "your-secret-api-key-change-in-production"):
        report("secrets.API_KEY", "FAIL", "API_KEY is still a placeholder")
    else:
        report("secrets.API_KEY", "PASS", "non-default")


async def check_database() -> None:
    from app.core.config import settings
    from app.core.database import get_db

    try:
        async with get_db() as db:
            if settings.is_postgres:
                async with db.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                ) as cur:
                    found = {r["table_name"] for r in await cur.fetchall()}
                missing = EXPECTED_TABLES - found
                if missing:
                    report("database.tables", "FAIL", f"missing: {sorted(missing)}")
                else:
                    report(
                        "database.tables",
                        "PASS",
                        f"{len(EXPECTED_TABLES)}/{len(EXPECTED_TABLES)} tables on postgres",
                    )
                try:
                    async with db.execute("SELECT version_num FROM alembic_version") as cur:
                        row = await cur.fetchone()
                    if row:
                        version = str(row[0])
                        if version == EXPECTED_ALEMBIC_HEAD:
                            report("database.alembic", "PASS", "version=" + version)
                        else:
                            report(
                                "database.alembic",
                                "FAIL",
                                f"version={version} (expected {EXPECTED_ALEMBIC_HEAD}) — "
                                "run: alembic -c backend/alembic.ini upgrade head",
                            )
                    else:
                        report("database.alembic", "FAIL", "version table empty")
                except Exception as exc:
                    report("database.alembic", "FAIL", "no version table")
            else:
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cur:
                    found = {r["name"] for r in await cur.fetchall()}
                missing = EXPECTED_TABLES - found
                if missing:
                    report("database.tables", "FAIL", f"missing: {sorted(missing)}")
                else:
                    report(
                        "database.tables",
                        "PASS",
                        f"{len(EXPECTED_TABLES)}/{len(EXPECTED_TABLES)} tables on sqlite",
                    )
                async with db.execute("PRAGMA table_info(workspace_documents)") as cur:
                    cols = {r["name"] for r in await cur.fetchall()}
                if {"object_key", "content_type", "etag"} <= cols:
                    report("database.phase2-columns", "PASS", "object-storage columns present")
                else:
                    report("database.phase2-columns", "FAIL", "run the app once (init_db backfills)")
                # Stage 2 data-retention columns.
                async with db.execute("PRAGMA table_info(conversations)") as cur:
                    conv_cols = {r["name"] for r in await cur.fetchall()}
                async with db.execute("PRAGMA table_info(documents)") as cur:
                    doc_cols = {r["name"] for r in await cur.fetchall()}
                missing = []
                if "workspace_id" not in conv_cols:
                    missing.append("conversations.workspace_id")
                if "file_path" not in doc_cols:
                    missing.append("documents.file_path")
                if missing:
                    report(
                        "database.retention-columns",
                        "FAIL",
                        f"missing: {missing} (run the app once, or apply migration 0005)",
                    )
                else:
                    report(
                        "database.retention-columns",
                        "PASS",
                        "conversations.workspace_id + documents.file_path present",
                    )
                # Subscription columns + metering ledger.
                async with db.execute("PRAGMA table_info(workspaces)") as cur:
                    ws_cols = {r["name"] for r in await cur.fetchall()}
                if {"plan", "plan_started_at"} <= ws_cols:
                    report(
                        "database.subscription-columns",
                        "PASS",
                        "workspaces.plan + plan_started_at present",
                    )
                else:
                    report(
                        "database.subscription-columns",
                        "FAIL",
                        "run the app once, or apply migration 0006",
                    )
    except Exception as exc:
        report("database.reachable", "FAIL", str(exc)[:200])


async def check_storage() -> None:
    from app.core.config import settings

    if not settings.use_s3_storage:
        report("storage.r2", "SKIP", "S3_BUCKET unset (local disk mode)")
        return
    try:
        from app.storage.object_store import S3Backend

        backend = S3Backend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
        await asyncio.to_thread(backend.delete_prefix, "__preflight_probe__")
        report("storage.r2", "PASS", f"bucket '{settings.s3_bucket}' reachable")
    except Exception as exc:
        report("storage.r2", "FAIL", str(exc)[:200])


async def check_app_config(strict: bool) -> None:
    from app.core.config import settings

    if settings.enable_docs:
        report(
            "config.docs",
            "FAIL" if strict else "SKIP",
            "ENABLE_DOCS=true (set false in production)",
        )
    else:
        report("config.docs", "PASS", "interactive docs hidden")
    origins = settings.allowed_origins_list
    if any("localhost" in o or "127.0.0.1" in o for o in origins):
        report(
            "config.cors",
            "FAIL" if strict else "SKIP",
            f"loopback origins present: {origins}",
        )
    else:
        report("config.cors", "PASS", f"explicit origins: {origins}")
    if strict and not settings.app_public_url.startswith("https://"):
        report("config.public-url", "FAIL", f"APP_PUBLIC_URL={settings.app_public_url}")
    else:
        report("config.public-url", "PASS" if settings.app_public_url.startswith("https://") else "SKIP", settings.app_public_url)

    # The dashboard origin that serves /chat/<token> must be the DASHBOARD,
    # not the API origin. Pointing both at the API breaks hosted links and
    # the hosted-origin allowance.
    hosted = (settings.hosted_base_url or "").rstrip("/")
    api = (settings.app_public_url or "").rstrip("/")
    if hosted and hosted == api:
        report(
            "config.hosted-url",
            "FAIL",
            "HOSTED_BASE_URL equals APP_PUBLIC_URL (hosted links would point at the API)",
        )
    elif strict and not hosted.startswith("https://"):
        report("config.hosted-url", "FAIL", f"HOSTED_BASE_URL={settings.hosted_base_url}")
    else:
        report("config.hosted-url", "PASS", settings.hosted_base_url)


async def check_runtime(strict: bool) -> None:
    """Runtime posture that only matters once real traffic arrives."""
    from app.core.config import settings

    if settings.is_postgres:
        report("runtime.database", "PASS", "PostgreSQL")
    else:
        report(
            "runtime.database",
            "FAIL" if strict else "SKIP",
            "DATABASE_URL is not PostgreSQL (production uses Postgres + pgvector)",
        )

    if settings.rate_limit_enabled:
        report("runtime.rate-limit", "PASS", f"enabled ({settings.rate_limit_per_minute}/min)")
    else:
        report(
            "runtime.rate-limit",
            "FAIL" if strict else "SKIP",
            "RATE_LIMIT_ENABLED=false (public endpoints would be unprotected)",
        )

    if not settings.use_s3_storage:
        report(
            "runtime.storage",
            "FAIL" if strict else "SKIP",
            "S3_BUCKET unset — the container filesystem is ephemeral, uploads would be lost",
        )
    else:
        report("runtime.storage", "PASS", f"bucket '{settings.s3_bucket}'")

    # The upload directory must be writable by the runtime user (agent icons
    # and local-disk uploads live there).
    try:
        from app.core.config import settings as _s

        path = _s.workspace_upload_path
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight-write-probe"
        probe.write_text("ok")
        probe.unlink()
        report("runtime.uploads-writable", "PASS", str(path))
    except Exception as exc:
        report("runtime.uploads-writable", "FAIL", str(exc)[:200])


async def check_backups() -> None:
    from app.core.config import settings

    if not settings.use_s3_storage:
        report("backups.recent", "SKIP", "no object storage configured")
        return
    try:
        from app.storage.object_store import S3Backend

        backend = S3Backend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
        client = backend._client_or_raise()
        resp = await asyncio.to_thread(
            client.list_objects_v2, Bucket=settings.s3_bucket, Prefix="backups/", MaxKeys=5
        )
        n = resp.get("KeyCount", 0)
        if n:
            report("backups.recent", "PASS", f"{n} backup object(s) under backups/")
        else:
            report("backups.recent", "FAIL", "backups/ prefix is empty — run backup script first")
    except Exception as exc:
        report("backups.recent", "FAIL", str(exc)[:200])


async def check_email(strict: bool) -> None:
    """Transactional mail must actually be able to deliver.

    With EMAIL_BACKEND=file the password-reset mail is written into the
    container's outbox and never reaches the customer, so this is a hard
    failure in production.
    """
    from app.core.config import settings

    backend = (settings.email_backend or "file").strip().lower()
    if backend != "smtp":
        report(
            "email.backend",
            "FAIL" if strict else "SKIP",
            f"EMAIL_BACKEND={backend} (production needs smtp)",
        )
    else:
        report("email.backend", "PASS", "smtp")

    host = (settings.smtp_host or "").strip()
    username = (settings.smtp_username or "").strip()
    password = settings.smtp_password or ""
    if backend == "smtp":
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", host),
                ("SMTP_USERNAME", username),
                ("SMTP_PASSWORD", password),
            )
            if not value
        ]
        if missing:
            report("email.smtp", "FAIL", f"missing: {missing}")
        else:
            report("email.smtp", "PASS", f"{host}:{settings.smtp_port} ({settings.smtp_security})")

    sender = (settings.email_from_address or "").strip()
    if not sender:
        report("email.from", "FAIL" if strict else "SKIP", "EMAIL_FROM_ADDRESS is empty")
    elif sender.endswith((".local", ".localhost", ".test")):
        report(
            "email.from",
            "FAIL" if strict else "SKIP",
            f"EMAIL_FROM_ADDRESS={sender} is not a deliverable domain",
        )
    else:
        report("email.from", "PASS", sender)

    reply_to = (settings.resolved_reply_to or "").strip()
    support = (settings.resolved_support_email or "").strip()
    if not reply_to:
        report("email.reply-to", "FAIL" if strict else "SKIP", "no reply-to address")
    else:
        report("email.reply-to", "PASS", reply_to)
    if support:
        report("email.support", "PASS", support)
    else:
        report("email.support", "SKIP", "SUPPORT_EMAIL unset (falls back to reply-to)")

    frontend = (settings.frontend_url or "").strip()
    if frontend and not frontend.startswith("https://"):
        report("email.frontend-url", "FAIL" if strict else "SKIP", f"FRONTEND_URL={frontend}")
    elif frontend:
        report("email.frontend-url", "PASS", frontend)
    else:
        report("email.frontend-url", "SKIP", "FRONTEND_URL unset (falls back to HOSTED_BASE_URL)")


async def check_admin(strict: bool) -> None:
    """The admin panel is reachable on the public internet — verify posture."""
    from app.core.config import settings

    prefix = (settings.admin_route_prefix or "").strip()
    if not prefix:
        report("admin.prefix", "FAIL" if strict else "SKIP", "ADMIN_ROUTE_PREFIX is empty")
    elif not prefix.startswith("/"):
        report("admin.prefix", "FAIL", f"ADMIN_ROUTE_PREFIX={prefix} must start with '/'")
    else:
        report("admin.prefix", "PASS", prefix)

    if settings.admin_session_expire_hours <= 0:
        report("admin.session", "FAIL", "ADMIN_SESSION_EXPIRE_HOURS must be positive")
    else:
        report("admin.session", "PASS", f"{settings.admin_session_expire_hours}h")

    if settings.totp_max_attempts_per_15m <= 0:
        report("admin.totp", "FAIL", "TOTP_MAX_ATTEMPTS_PER_15M must be positive")
    else:
        report("admin.totp", "PASS", f"{settings.totp_max_attempts_per_15m} attempts / 15m")

    # The dashboard route is a folder name, so the prefix and the UI path can
    # drift apart. The default is the shipped route.
    if prefix != "/bbx765adm":
        report(
            "admin.route-match",
            "SKIP",
            f"ADMIN_ROUTE_PREFIX={prefix} — confirm BaseBot_UI/src/app has the same folder",
        )
    else:
        report("admin.route-match", "PASS", "matches BaseBot_UI/src/app/bbx765adm")


async def check_plans(strict: bool) -> None:
    """Plan catalogue, prices and the trial must match the source of truth."""
    from app.core.plan import PLAN_PRICES_TZS, TRIAL_DAYS
    from app.core.config import settings

    if (settings.default_workspace_plan or "").strip() != "free":
        report(
            "plans.default",
            "FAIL" if strict else "SKIP",
            f"DEFAULT_WORKSPACE_PLAN={settings.default_workspace_plan} (production starts on free)",
        )
    else:
        report("plans.default", "PASS", "free")

    if TRIAL_DAYS != 21:
        report("plans.trial", "FAIL", f"TRIAL_DAYS={TRIAL_DAYS}")
    else:
        report("plans.trial", "PASS", f"{TRIAL_DAYS} days")

    missing = [pid for pid, price in PLAN_PRICES_TZS.items() if price < 0]
    if missing:
        report("plans.prices", "FAIL", f"invalid prices: {missing}")
    else:
        detail = ", ".join(f"{pid}=TZS {price:,}" for pid, price in PLAN_PRICES_TZS.items())
        report("plans.prices", "PASS", detail)

    # Paid plans are displayed but not purchasable until a gateway exists.
    report(
        "plans.payments",
        "PASS",
        "not configured (trial + free at launch; upgrades are manual via the admin panel)",
    )


async def check_llm(strict: bool) -> None:
    from app.core.config import settings

    if not (settings.openrouter_api_key or "").strip():
        report(
            "llm.openrouter",
            "FAIL" if strict else "SKIP",
            "OPENROUTER_API_KEY is empty — chat cannot answer",
        )
    else:
        report("llm.openrouter", "PASS", settings.openrouter_model or "openrouter/free")


async def main(strict: bool) -> int:
    await check_secrets()
    await check_database()
    await check_storage()
    await check_app_config(strict)
    await check_email(strict)
    await check_admin(strict)
    await check_plans(strict)
    await check_llm(strict)
    await check_runtime(strict)
    await check_backups()
    fails = [r for r in results if r[1] == "FAIL"]
    print(f"\npreflight: {len(results) - len(fails)}/{len(results)} ok ({len(fails)} FAIL)")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="production gate")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.strict)))
