"""
scripts/backup_postgres_to_r2.py (Phase 4)
Nightly-backup primitive: database bytes -> R2/S3 versioned bucket.

  --dry-run    show what would be backed up (no writes)
  --pg         pg_dump (custom format) the Postgres DATABASE_URL to
               backups/pg/<utc-timestamp>.dump  (needs pg_dump + S3 configured)
  --sqlite     upload the local SQLite file to backups/sqlite/<ts>.db

R2 bucket versioning + lifecycle (noncurrent expiry) is configured once in
the Cloudflare dashboard, not here. Neon PITR covers point-in-time recovery;
these dumps are the portable second copy (and the restore path for a move
between providers).

Suggested cron (host or PaaS scheduled job):
  0 2 * * * cd /opt/xvec && DATABASE_URL=... S3_BUCKET=... python scripts/backup_postgres_to_r2.py --pg
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def _put_to_r2(key: str, data: bytes) -> None:
    from app.core.config import settings
    from app.storage.object_store import S3Backend

    if not settings.use_s3_storage:
        raise RuntimeError("S3 storage is not configured (S3_BUCKET).")
    backend = S3Backend(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.aws_access_key_id,
        secret_key=settings.aws_secret_access_key,
    )
    await asyncio.to_thread(
        backend.put_object, key, data, "application/octet-stream"
    )
    head = await asyncio.to_thread(backend.head_object, key)
    print(f"stored: {key} ({head.size_bytes if head else len(data)} bytes)")


async def backup_sqlite() -> int:
    from app.core.config import settings

    if settings.is_postgres:
        print("DATABASE_URL is Postgres — use --pg for this host.")
        return 2
    src = settings.database_path
    if not src.is_file():
        print(f"no SQLite file at {src} — nothing to back up.")
        return 1
    key = f"{settings.s3_prefix.strip().strip('/')}/backups/sqlite/{_stamp()}.db".lstrip("/")
    data = await asyncio.to_thread(src.read_bytes)
    await _put_to_r2(key, data)
    return 0


async def backup_pg() -> int:
    import os

    from app.core.config import settings

    if not settings.is_postgres:
        print("DATABASE_URL is not Postgres — use --sqlite for local files.")
        return 2
    if shutil.which("pg_dump") is None:
        print("pg_dump binary not found on PATH — install postgresql-client.")
        return 1
    dsn = settings.asyncpg_dsn
    key = f"{settings.s3_prefix.strip().strip('/')}/backups/pg/{_stamp()}.dump".lstrip("/")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp:
        tmp_path = tmp.name
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["pg_dump", "--format=custom", "--no-owner", f"--dbname={dsn}", f"--file={tmp_path}"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"pg_dump failed: {proc.stderr.strip()[:500]}")
            return 1
        data = await asyncio.to_thread(Path(tmp_path).read_bytes)
        if not data:
            print("pg_dump produced an empty file — aborting upload.")
            return 1
        await _put_to_r2(key, data)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    keep = int(os.environ.get("BACKUP_KEEP_DAYS", "0") or 0)
    if keep:
        print(f"(retention: configure R2 lifecycle to expire backups/ after {keep}d)")
    return 0


async def dry_run() -> int:
    from app.core.config import settings

    print(f"database: {'postgres' if settings.is_postgres else 'sqlite'}")
    if not settings.is_postgres:
        p = settings.database_path
        print(f"  file: {p} ({p.stat().st_size if p.is_file() else 'missing'} bytes)")
    else:
        print(f"  dsn host: {settings.asyncpg_dsn.split('@')[-1][:40]}…")
        print(f"  pg_dump on PATH: {shutil.which('pg_dump') is not None}")
    print(f"storage: {'s3/r2' if settings.use_s3_storage else 'local (set S3_BUCKET to enable)'}")
    if settings.use_s3_storage:
        print(f"  bucket: {settings.s3_bucket} prefix: {settings.s3_prefix}")
    print("dry-run OK (use --pg or --sqlite to write a backup)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pg", action="store_true")
    ap.add_argument("--sqlite", action="store_true")
    args = ap.parse_args()
    if args.pg:
        return asyncio.run(backup_pg())
    if args.sqlite:
        return asyncio.run(backup_sqlite())
    return asyncio.run(dry_run())


if __name__ == "__main__":
    raise SystemExit(main())
