"""
scripts/backfill_uploads_to_r2.py (Phase 2)
Upload local workspace files to R2/S3 and stamp object_key on their rows.

Usage:
  python scripts/backfill_uploads_to_r2.py --dry-run   # list what would upload
  S3_BUCKET=... S3_ENDPOINT_URL=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
    python scripts/backfill_uploads_to_r2.py --copy

Idempotent: rows that already have object_key are skipped; S3 puts overwrite
the same key. Legacy local files are left in place (delete manually after
verifying training reads from object storage).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def collect() -> list[dict]:
    from app.core.database import get_db

    async with get_db() as db:
        # object_key may not exist on very old DBs — init_db adds it at boot,
        # but tolerate its absence here with a file_path-only listing.
        try:
            async with db.execute(
                "SELECT id, workspace_id, filename, file_path, object_key "
                "FROM workspace_documents"
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        except Exception:
            async with db.execute(
                "SELECT id, workspace_id, filename, file_path "
                "FROM workspace_documents"
            ) as cur:
                rows = [{**dict(r), "object_key": None} for r in await cur.fetchall()]
    return rows


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--copy", action="store_true")
    args = ap.parse_args()

    rows = await collect()
    pending = [r for r in rows if not r.get("object_key")]
    print(f"documents: {len(rows)} total, {len(pending)} without object_key")
    if args.dry_run or not args.copy:
        for r in pending[:20]:
            print(f"  would upload: {r['id']} {r['filename']} <- {r['file_path']}")
        if len(pending) > 20:
            print(f"  ... and {len(pending) - 20} more")
        print("dry-run OK (use --copy with S3_* env to upload)")
        return 0

    from app.core.config import settings
    from app.core.database import get_db
    from app.storage.object_store import build_object_key, content_type_for, get_storage

    if not settings.use_s3_storage:
        print("S3 storage is not configured (S3_BUCKET). Aborting.")
        return 2
    storage = get_storage()
    uploaded = skipped = failed = 0
    async with get_db() as db:
        for r in pending:
            src = Path(r["file_path"]) if r.get("file_path") else None
            if src is None or not src.is_file():
                print(f"  skip (missing file): {r['id']} {r.get('file_path')}")
                skipped += 1
                continue
            key = build_object_key(
                r["workspace_id"], r["id"], r["filename"], settings.s3_prefix
            )
            try:
                data = await asyncio.to_thread(src.read_bytes)
                await asyncio.to_thread(
                    storage.put_object, key, data, content_type_for(r["filename"])
                )
                head = await asyncio.to_thread(storage.head_object, key)
                await db.execute(
                    "UPDATE workspace_documents SET object_key = ?, content_type = ?, "
                    "size_bytes = ?, etag = ? WHERE id = ?",
                    (
                        key,
                        content_type_for(r["filename"]),
                        head.size_bytes if head else len(data),
                        head.etag if head else None,
                        r["id"],
                    ),
                )
                await db.commit()
                uploaded += 1
                print(f"  uploaded: {r['id']} -> {key}")
            except Exception as exc:
                print(f"  FAILED: {r['id']}: {exc}")
                failed += 1
    print(f"done: uploaded={uploaded} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
