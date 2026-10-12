# Production Deployment Guide — XvecBot as a Real PaaS

From a local checkout to a public platform real users can sign up on.
Follow top to bottom; each step gates the next. Your local setup is never
modified by any of this — production activates purely via environment.

**Time estimate:** ~2–3 hours first time (mostly waiting on DNS + builds).

---

## 0. What you need (accounts + decisions)

| # | Account / decision | Recommended | Why |
|---|---|---|---|
| 1 | Managed Postgres + pgvector | **Neon** (serverless, free tier) — alternatives: Supabase, RDS, Cloud SQL | Multi-user writes, pooled connections, PITR backups; SQLite can't do this |
| 2 | Object storage (S3 API) | **Cloudflare R2** (zero egress fees) — alternatives: AWS S3, GCS | Document bytes; browsers upload/download directly via presigned URLs |
| 3 | Container hosting | **Render, Fly.io, or Railway** | Runs `docker/compose.prod.yml` services; healthchecks + env dashboards built in |
| 4 | Domain + DNS | Any registrar (e.g. Cloudflare) | `app.yourdomain.com` (dashboard) + `api.yourdomain.com` (backend), TLS auto |
| 5 | LLM key | OpenRouter (paid tier for real traffic) | Free-tier models rate-limit under real load |
| 6 | `SECRET_KEY` + `API_KEY` | Generate now, store in a password manager | `python3 -c "import secrets;print(secrets.token_hex(32))"` (×2) |

Keep your local `.env` exactly as it is. All production values live in the
hosting dashboards, never in the repo (the image does **not** bake `.env`).

---

## 1. Provision Neon (Postgres + pgvector)

1. Create a project + database (region closest to your users/hosting).
2. In the Neon SQL editor, run: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Copy two connection strings:
   - **Pooled** (`…-pooler…?sslmode=require`) → app `DATABASE_URL`
   - **Direct** → one-off `psql` / `pg_dump` admin work
4. Note the connection limit of your tier; keep `PG_POOL_MAX_SIZE` (default
   10) × `UVICORN_WORKERS` (default 2) × replicas under it.

## 2. Provision R2 (bucket, CORS, lifecycle)

1. Create bucket `xvecbot-prod` (or your name → `S3_BUCKET`).
2. **CORS** (browsers PUT directly): allow `PUT, GET, HEAD` from
   `https://app.yourdomain.com` (add staging origin too while testing).
3. **Lifecycle**: expire noncurrent versions under `backups/` after 30 days;
   keep versioning ON (accidental deletes are recoverable).
4. Create an API token with Object Read/Write on that bucket →
   `S3_ENDPOINT_URL` (`https://<accountid>.r2.cloudflarestorage.com`),
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. `S3_PREFIX=xvecbot`,
   `S3_REGION=auto`.

## 3. Deploy the backend (staging first)

On your PaaS, create the API service from `docker/Dockerfile.backend` (or
`docker/compose.prod.yml`) with this env (staging values first):

| Var | Staging value |
|---|---|
| `DEBUG` | `false` |
| `ENABLE_DOCS` | `false` |
| `UVICORN_WORKERS` | `2` |
| `DATABASE_URL` | Neon pooled URL |
| `SECRET_KEY` / `API_KEY` | generated (staging set is fine) |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | your key / model |
| `ALLOWED_ORIGINS` | `https://<staging-dashboard-url>` |
| `APP_PUBLIC_URL` | `https://<staging-api-url>` |
| `STORAGE_BACKEND` | `auto` |
| `S3_BUCKET` / `S3_PREFIX` / `S3_ENDPOINT_URL` / `S3_REGION` / `AWS_*` | from §2 |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_PER_MINUTE` | `true` / `60` |
| `LOG_LEVEL` | `INFO` |

Boot behavior to expect in logs: `Postgres database ready` (schema auto-
creates), embedding warmup (~15–60 s), then `/health/ready` → 200. If the
service refuses to start with the `SECRET_KEY` error, the env didn't land —
fix that before anything else.

Run migrations explicitly (belt and suspenders — boot already applies them):

```bash
DATABASE_URL="<neon-pooled>" .venv/bin/python -m alembic -c backend/alembic.ini upgrade head
# → 0002_ws_docs_object_storage, 11 tables + alembic_version
```

## 4. Migrate your data (SQLite → Neon, files → R2)

From any machine with repo + network (local laptop is fine):

```bash
# 1. relational + vectors (idempotent, re-runnable)
DATABASE_URL="<neon-pooled>" .venv/bin/python scripts/migrate_sqlite_to_neon.py --copy
# expect: 1:1 counts per table + chunk_embeddings

# 2. file bytes (idempotent; skips rows that already have object_key)
S3_BUCKET=... S3_ENDPOINT_URL=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
  .venv/bin/python scripts/backfill_uploads_to_r2.py --copy

# 3. portable snapshot to R2 (before first real users)
DATABASE_URL="<neon-pooled>" S3_BUCKET=... ... \
  .venv/bin/python scripts/backup_postgres_to_r2.py --pg
```

## 5. Gate, then deploy the dashboard

```bash
# must exit 0 — any FAIL blocks go-live
DATABASE_URL="<neon-pooled>" S3_BUCKET=... ... \
  .venv/bin/python scripts/cutover_preflight.py --strict
```

Build the dashboard image with **build args** (they bake in at build time —
changing the API URL later means rebuilding):

```
NEXT_PUBLIC_API_BASE_URL=https://<staging-api-url>
NEXT_PUBLIC_APP_NAME=XvecBot
NEXT_PUBLIC_SITE_URL=https://<staging-dashboard-url>
```

Then smoke it:

```bash
.venv/bin/python scripts/staging_smoke.py --base-url https://<staging-api-url>
# all steps ok (drop --no-chat only if staging has an LLM key)
```

## 6. Go live (DNS → prod deploy → verify)

1. Point DNS: `api.` → backend service, `app.` → dashboard. Wait for TLS.
2. Redeploy both services with **prod** env (fresh `SECRET_KEY`, prod
   `ALLOWED_ORIGINS` = exactly `https://app.yourdomain.com`, prod R2 creds
   if separate).
3. Re-run `--strict` preflight + smoke against prod (with `--no-chat` first,
   then one real chat to prove the LLM path).
4. Invite 2–3 pilot users before announcing.

## 7. Operate (backups, monitoring, costs)

- **Backups cron** (daily, host or PaaS scheduled job):
  `backup_postgres_to_r2.py --pg`, plus confirm R2 lifecycle expires old
  `backups/`. Neon PITR covers point-in-time; dumps are the portable copy.
- **Watch**: 5xx rate, p95 chat latency, `/health/ready` 503s, R2 4xx
  (usually CORS), rate-limit 429 spikes (tune `RATE_LIMIT_PER_MINUTE`).
- **Costs to expect**: Neon (compute + storage over free tier), R2
  (storage ~free, egress free), PaaS (2 services, smallest tier to start),
  OpenRouter (per-token — set `LLM_MAX_TOKENS`/`LLM_FALLBACK_MODEL` sane).
- **Rollback**: flip dashboard build arg back to the previous API URL and
  redeploy; for data, restore the Neon snapshot / latest R2 dump. Keep the
  SQLite file as read-only fallback for 14 days post-launch.

## 8. Troubleshooting go-live

| Symptom | Fix |
|---|---|
| Service refuses boot (`SECRET_KEY` error) | Real 32+ hex `SECRET_KEY` with `DEBUG=false` |
| `/health/ready` 503 | `DATABASE_URL` wrong/unreachable; check pooler URL + `sslmode=require` |
| Browser upload CORS error | R2 CORS must allow `PUT,GET,HEAD` from the exact dashboard origin |
| `complete-upload` 400 "PUT the bytes first" | Presigned URL expired (15 min) or PUT failed — mint again |
| Chat 401/402 via OpenRouter | Bad key / no credits — top up, key is per-environment |
| Dashboard talks to localhost in prod | Rebuild with prod `NEXT_PUBLIC_API_BASE_URL` (it's baked, not runtime) |
| 429 on legit traffic | Raise `RATE_LIMIT_PER_MINUTE` (note: value is per-process × workers) |

---

## Appendix — local Docker testing (unchanged by all of the above)

```bash
export UID GID   # bind-mounted files keep your ownership (see phase4.md)
docker compose -f docker/docker-compose.yml up --build -d
.venv/bin/python scripts/staging_smoke.py --base-url http://127.0.0.1:8000 --no-chat
```

`phase2.md` (§2–§11) remains the manual curl walkthrough; `phase3/4/5.md`
are the execution records (local notes, gitignored, kept on disk).
