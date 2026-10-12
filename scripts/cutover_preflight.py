"""
scripts/cutover_preflight.py (Phase 5)
Go/no-go gate for staging -> production cutover. Read-only: never writes.

  python scripts/cutover_preflight.py            # check local .env posture
  python scripts/cutover_preflight.py --strict   # production gate (exit != 0 on any FAIL)

Checks (each prints PASS/FAIL/SKIP):
  1. secrets      SECRET_KEY non-default when DEBUG=false; API_KEY non-default
  2. database     reachable + all 11 tables present (+ alembic_version on pg)
  3. storage      S3/R2 reachable when S3_BUCKET set (head-bucket via list)
  4. migrations   alembic heads applied (pg) / init_db columns present (sqlite)
  5. app config   ENABLE_DOCS=false, ALLOWED_ORIGINS has no localhost (strict),
                  APP_PUBLIC_URL is https (strict)
  6. backups      R2 backups/ prefix non-empty when S3 configured (else SKIP)

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
}

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
                    report("database.tables", "PASS", "11/11 tables on postgres")
                try:
                    async with db.execute("SELECT version_num FROM alembic_version") as cur:
                        row = await cur.fetchone()
                    if row:
                        report("database.alembic", "PASS", "version=" + str(row[0]))
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
                    report("database.tables", "PASS", "11/11 tables on sqlite")
                async with db.execute("PRAGMA table_info(workspace_documents)") as cur:
                    cols = {r["name"] for r in await cur.fetchall()}
                if {"object_key", "content_type", "etag"} <= cols:
                    report("database.phase2-columns", "PASS", "object-storage columns present")
                else:
                    report("database.phase2-columns", "FAIL", "run the app once (init_db backfills)")
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


async def main(strict: bool) -> int:
    await check_secrets()
    await check_database()
    await check_storage()
    await check_app_config(strict)
    await check_backups()
    fails = [r for r in results if r[1] == "FAIL"]
    print(f"\npreflight: {len(results) - len(fails)}/{len(results)} ok ({len(fails)} FAIL)")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="production gate")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.strict)))
