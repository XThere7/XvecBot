"""
scripts/migrate_sqlite_to_neon.py (Phase 0+1)
Dry-run parity + full SQLite -> Postgres (Neon) copy.

Usage:
  python scripts/migrate_sqlite_to_neon.py --dry-run        # sqlite counts + vector decode check
  DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_neon.py --copy

Copy order respects REFERENCES. Embeddings are decoded from the sqlite-vec
blob (struct little-endian floats) into pgvector lists. Idempotent: all
inserts use ON CONFLICT DO NOTHING (re-runnable).
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TABLES_IN_ORDER = [
    "documents",
    "users",
    "workspaces",
    "workspace_documents",
    "agents",
    "conversations",
    "messages",
    "chunks",
]

SQLITE_DB = ROOT / "data" / "rag.db"


def _connect_sqlite(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    try:
        import sqlite_vec

        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
    except Exception as exc:
        print(f"  (sqlite-vec extension not loaded: {exc})")
    return con


def sqlite_counts(db_path: Path) -> dict:
    con = _connect_sqlite(db_path)
    out = {}
    for t in [*TABLES_IN_ORDER, "chunk_embeddings"]:
        try:
            out[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except Exception as exc:
            out[t] = f"ERR {exc}"
    con.close()
    return out


def decode_vec_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def dry_run() -> int:
    print(f"sqlite: {SQLITE_DB} (exists={SQLITE_DB.exists()})")
    if not SQLITE_DB.exists():
        print("nothing to check")
        return 0
    counts = sqlite_counts(SQLITE_DB)
    for t, c in counts.items():
        print(f"  {t}: {c}")
    con = _connect_sqlite(SQLITE_DB)
    try:
        row = con.execute(
            "SELECT chunk_id, embedding FROM chunk_embeddings LIMIT 1"
        ).fetchone()
    except Exception as exc:
        print(f"  embeddings sample: ERR {exc}")
        return 0
    if row is None:
        print("  embeddings sample: empty table")
        return 0
    vec = decode_vec_blob(row[1])
    print(f"  embeddings sample: chunk={row[0][:8]}… dim={len(vec)}")
    assert len(vec) == 384, f"expected dim 384, got {len(vec)}"
    print("dry-run OK (dim 384, counts recorded)")
    return 0


async def copy_to_postgres(dsn: str) -> int:
    import asyncpg

    from pgvector.asyncpg import register_vector

    conn = await asyncpg.connect(dsn)
    try:
        # Schema first (same DDL the app boots with) — extension must exist
        # before the pgvector codec is registered on this connection.
        from app.core.pg_schema import PG_PREABLE, PG_TABLES

        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        for stmt in (s.strip() for s in PG_TABLES.split(";")):
            if stmt:
                await conn.execute(stmt)

        scon = _connect_sqlite(SQLITE_DB)
        scon.row_factory = sqlite3.Row
        total = 0
        for table in TABLES_IN_ORDER:
            try:
                rows = scon.execute(f"SELECT * FROM {table}").fetchall()
            except Exception as exc:
                print(f"  skip {table}: {exc}")
                continue
            if not rows:
                print(f"  {table}: 0 rows")
                continue
            cols = rows[0].keys()
            collist = ", ".join(cols)
            for r in rows:
                vals = [r[c] for c in cols]
                ph = ", ".join(f"${i + 1}" for i in range(len(cols)))
                await conn.execute(
                    f"INSERT INTO {table} ({collist}) VALUES ({ph}) "
                    "ON CONFLICT DO NOTHING",
                    *vals,
                )
            total += len(rows)
            print(f"  {table}: {len(rows)} rows")
        # Embeddings: blob -> list[float], chunk context from chunks.
        try:
            erows = scon.execute(
                "SELECT chunk_id, embedding FROM chunk_embeddings"
            ).fetchall()
        except Exception as exc:
            print(f"  chunk_embeddings: ERR {exc}")
            erows = []
        n_emb = 0
        for chunk_id, blob in erows:
            vec = decode_vec_blob(blob)
            crow = scon.execute(
                "SELECT workspace_id, doc_id FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            ws, dd = (crow[0], crow[1]) if crow else (None, None)
            await conn.execute(
                """INSERT INTO chunk_embeddings
                   (chunk_id, workspace_id, doc_id, embedding)
                   VALUES ($1,$2,$3,$4) ON CONFLICT (chunk_id) DO NOTHING""",
                chunk_id,
                ws,
                dd,
                vec,
            )
            n_emb += 1
        print(f"  chunk_embeddings: {n_emb} rows | relational total: {total}")
        # Verify.
        for t in [*TABLES_IN_ORDER, "chunk_embeddings"]:
            c = await conn.fetchval(f"SELECT count(*) FROM {t}")
            print(f"  pg {t}: {c}")
    finally:
        await conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--copy", action="store_true")
    args = ap.parse_args()
    if args.copy:
        import os

        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn.lower().startswith(("postgresql://", "postgres://")):
            print("DATABASE_URL must be postgresql://… for --copy")
            return 2
        return asyncio.run(copy_to_postgres(dsn))
    return dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
