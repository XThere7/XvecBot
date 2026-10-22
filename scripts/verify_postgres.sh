#!/usr/bin/env bash
# scripts/verify_postgres.sh — one command that proves the PostgreSQL path.
#
# Runs, in order:
#   1. the full pytest suite against SQLite (default engine)
#   2. the full pytest suite against a real PostgreSQL + pgvector
#   3. Alembic migrations against PostgreSQL (head = 0004_developer_api_keys)
#   4. the full customer-journey E2E against a Postgres-backed API
#   5. (optional) the presigned object-storage E2E when an S3 endpoint is set
#
# This is the gate that used to be missing: the Postgres code path
# (asyncpg pool, pg_compat '?' -> '$n' translation, pgvector KNN, BM25 over
# Postgres rows) now has automated coverage on every run.
#
# USAGE
#   bash scripts/verify_postgres.sh
#
#   Optional:
#     E2E_S3_ENDPOINT=http://127.0.0.1:9000  run the storage E2E too
#     E2E_S3_BUCKET=botbase
#     E2E_S3_KEY=minioadmin  E2E_S3_SECRET=minioadmin
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="${PYTHON:-python3}"

PGHOME="${PGHOME:-$HOME/.local/share/botbase-pg}"
DSN="${E2E_DSN:-postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase_verify}"
API="${E2E_API:-http://127.0.0.1:8010}"
UPLOADS="${E2E_UPLOAD_DIR:-/tmp/botbase-verify-uploads}"

log() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

cleanup() {
  if [ -n "${API_PID:-}" ]; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

log "1/5 pytest suite on SQLite (default engine)"
cd "$ROOT/backend"
PYTHONPATH=. "$PY" -m pytest app/tests/ -q

log "2/5 pytest suite on PostgreSQL"
if ! "$ROOT/scripts/dev_postgres.sh" status | grep -q up; then
  "$ROOT/scripts/dev_postgres.sh" start
fi
export BOTBASE_TEST_DATABASE_URL="$DSN"
# The scratch database for the suite (separate from the E2E database).
"$PY" - <<'PY'
import asyncio, os, asyncpg
async def main():
    dsn = os.environ["BOTBASE_TEST_DATABASE_URL"]
    conn = await asyncpg.connect(dsn)
    await conn.close()
try:
    asyncio.run(main())
except Exception:
    pass
PY
PYTHONPATH=. "$PY" -m pytest app/tests/ -q
unset BOTBASE_TEST_DATABASE_URL

log "3/5 Alembic migrations on PostgreSQL"
PYTHONPATH=. "$PY" -m alembic -c backend/alembic.ini upgrade head
PGPASSWORD=botbase_pw psql -h 127.0.0.1 -p 5433 -U botbase -d botbase_verify \
  -tAc "SELECT version_num FROM alembic_version;"

log "4/5 customer-journey E2E on PostgreSQL"
rm -rf "$UPLOADS"; mkdir -p "$UPLOADS"
DATABASE_URL="$DSN" UPLOAD_DIR="$UPLOADS" PROCESSED_DIR="${UPLOADS}/processed" \
  SECRET_KEY=verify-secret-key-0123456789abcdef0123456789abcdef \
  API_KEY=verify-legacy-key APP_PUBLIC_URL="$API" \
  HOSTED_BASE_URL=http://localhost:3000 ALLOWED_ORIGINS=http://localhost:3000 \
  RATE_LIMIT_ENABLED=true ENABLE_DOCS=true DEBUG=false \
  PYTHONPATH=. "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 \
  > /tmp/botbase-verify-api.log 2>&1 &
API_PID=$!
for _ in $(seq 1 90); do
  curl -fsS "$API/health/ready" >/dev/null 2>&1 && break
  sleep 2
done
E2E_API="$API" E2E_DSN="$DSN" E2E_UPLOAD_DIR="$UPLOADS" \
  "$PY" "$ROOT/scripts/e2e_postgres.py"

if [ -n "${E2E_S3_ENDPOINT:-}" ]; then
  log "5/5 presigned object-storage E2E"
  E2E_API="$API" E2E_S3_ENDPOINT="$E2E_S3_ENDPOINT" \
    E2E_S3_BUCKET="${E2E_S3_BUCKET:-botbase}" \
    E2E_S3_KEY="${E2E_S3_KEY:-minioadmin}" \
    E2E_S3_SECRET="${E2E_S3_SECRET:-minioadmin}" \
    "$PY" "$ROOT/scripts/e2e_storage.py"
else
  log "5/5 presigned object-storage E2E — skipped (set E2E_S3_ENDPOINT to run)"
fi

log "ALL POSTGRES VERIFICATION PASSED"
