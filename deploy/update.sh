#!/usr/bin/env bash
# deploy/update.sh — safe, manual release of the BotBase API.
#
# What it does, in order:
#   1. snapshot the current images (so a rollback is one command)
#   2. git pull (the code you pushed)
#   3. rebuild the images
#   4. run the database migrations against the NEW image (before it serves)
#   5. start the new containers
#   6. wait for /health/ready
#   7. if the new version is unhealthy for 90 seconds -> roll back to the
#      previous image and exit non-zero
#
# Usage (on the VPS):
#   bash deploy/update.sh
#
# Downtime: the API is unavailable for roughly 30-90 seconds while the
# containers restart. Do it in a quiet window; the dashboard on Vercel keeps
# serving (it will show a brief "cannot reach the server" error).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/opt/botbase/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker/compose.prod.yml}"
HEALTH_URL="${HEALTH_URL:-http://localhost/health/ready}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

cd "$ROOT"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

log() { printf '\033[1;36m[update]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[update] %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE (see deploy/env.example)"

# ── 1. snapshot the running image so we can roll back ────────────────────────
PREV_BACKEND="$(compose images -q backend 2>/dev/null || true)"
if [ -n "$PREV_BACKEND" ]; then
  docker tag "$PREV_BACKEND" botbase-backend:prev || true
  log "previous backend image tagged botbase-backend:prev"
fi

# ── 2. pull the new code ─────────────────────────────────────────────────────
if [ -d .git ]; then
  log "git pull"
  git pull --ff-only || die "git pull failed (resolve locally, then re-run)"
fi

# ── 3. build ─────────────────────────────────────────────────────────────────
log "building images (this can take a few minutes)"
compose build || die "image build failed"

# ── 4. migrate with the new code, before it serves traffic ──────────────────
log "running database migrations"
compose run --rm --no-deps backend alembic -c backend/alembic.ini upgrade head \
  || die "migrations failed — the old containers are still running"

# ── 5. start the new version ─────────────────────────────────────────────────
log "starting the new version"
compose up -d --remove-orphans || die "compose up failed"

# ── 6. health gate ───────────────────────────────────────────────────────────
log "waiting for $HEALTH_URL (timeout ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
healthy=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 3
done

# ── 7. roll back if unhealthy ────────────────────────────────────────────────
if [ "$healthy" -ne 1 ]; then
  printf '\033[1;31m[update] new version is unhealthy — rolling back\033[0m\n' >&2
  compose logs --tail=80 backend >&2 || true
  if [ -n "$PREV_BACKEND" ]; then
    docker tag botbase-backend:prev "$PREV_BACKEND" || true
    compose up -d --no-deps backend || true
    log "rolled back to the previous image"
  fi
  die "deployment failed"
fi

log "healthy — release complete"
compose ps
