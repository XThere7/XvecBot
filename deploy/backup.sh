#!/usr/bin/env bash
# deploy/backup.sh — nightly database backup to object storage.
#
# Runs inside the API container (it has pg_dump and the S3 client) and
# uploads a custom-format dump to  <bucket>/backups/pg/<timestamp>.dump
#
# Usage (on the VPS):
#   bash deploy/backup.sh              # one backup now
#   crontab -e
#     17 3 * * * cd /opt/botbase && bash deploy/backup.sh >> /var/log/botbase-backup.log 2>&1
#
# The dump is portable: restoring it works on any Postgres (see deploy/restore.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/opt/botbase/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker/compose.prod.yml}"
KEEP_DAYS="${KEEP_DAYS:-14}"

cd "$ROOT"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

log() { printf '\033[1;36m[backup]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[backup] %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE"

log "dumping the database and uploading it to object storage"
compose exec -T backend python scripts/backup_postgres_to_r2.py --pg \
  || die "backup failed"

log "done — configure an S3/R2 lifecycle rule to expire backups/pg/ after ${KEEP_DAYS} days"
log "REMINDER: a backup is only real once you have restored it (see deploy/restore.md)"
