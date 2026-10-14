# Production Deployment Guide — BotBase as a Real PaaS

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
| 3 | Hosting | **Vercel for the dashboard** (`BaseBot_UI/`), **Render / Fly.io / Railway for the backend** (containers) | Vercel is purpose-built for Next.js (previews, edge, zero config); the API stays on a container host with healthchecks + env dashboards |
| 4 | Domain + DNS | Any registrar (e.g. Cloudflare) | `app.yourdomain.com` (dashboard → Vercel) + `api.yourdomain.com` (backend) , TLS auto on both |
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

1. Create bucket `botbase-prod` (or your name → `S3_BUCKET`).
2. **CORS** (browsers PUT directly): allow `PUT, GET, HEAD` from
   `https://app.yourdomain.com` (add staging origin too while testing).
3. **Lifecycle**: expire noncurrent versions under `backups/` after 30 days;
   keep versioning ON (accidental deletes are recoverable).
4. Create an API token with Object Read/Write on that bucket →
   `S3_ENDPOINT_URL` (`https://<accountid>.r2.cloudflarestorage.com`),
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. `S3_PREFIX=botbase`,
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

## 5. Deploy the dashboard on Vercel

The dashboard (`BaseBot_UI/`, Next.js 15) deploys to Vercel — no Dockerfile,
no `vercel.json` needed. The only thing that changes per environment is three
public env vars (they bake into the browser bundle **at build time**, so
changing them always needs a redeploy).

### 5.1 One-time project setup

1. Push the repo (see note on phase docs below), then Vercel → Add New →
   Project → import it.
2. **Root Directory → `BaseBot_UI`** (repo root has no Next.js app; without
   this the build finds nothing). Framework Preset auto-detects Next.js —
   leave Build Command (`next build`), Output, and Install (`npm ci`) default.
3. Node version: any 20+ default Vercel offers (repo uses Node 20 locally).
4. Create **two environments worth of values** — fill Production now, add the
   staging ones when you create a Preview/staging branch:
   - `NEXT_PUBLIC_API_BASE_URL` → `https://<api-url>` (staging or prod —
     **no trailing slash**)
   - `NEXT_PUBLIC_APP_NAME` → `BotBase`
   - `NEXT_PUBLIC_SITE_URL` → `https://<dashboard-url>`
5. Deploy. First build takes a few minutes (`npm ci` + Next build).

> `next.config.ts` sets `output: "standalone"` for the self-hosted Docker
> frontend (`docker/Dockerfile.frontend`). Vercel ignores it and uses its own
> output — **do not remove it**, Docker needs it. Likewise `images:
> unoptimized` stays as-is.

### 5.2 Custom domain + previews

1. Vercel → Project → Settings → Domains → add `app.yourdomain.com`
   (staging: e.g. `staging-app.yourdomain.com` on a second project or a
   Preview deployment). DNS as instructed by Vercel; TLS is automatic.
2. Every PR/branch gets a Preview URL automatically — perfect for testing
   dashboard changes against the **staging** API (set Preview env vars to
   the staging URLs once).
3. After adding/changing *any* env var: **Redeploy** (Vercel → Deployments →
   ⋯ → Redeploy) — edited vars don't apply to existing builds.

### 5.3 Gate, then smoke

```bash
# must exit 0 — any FAIL blocks go-live
DATABASE_URL="<neon-pooled>" S3_BUCKET=... ... \
  .venv/bin/python scripts/cutover_preflight.py --strict
```

Then smoke the API (dashboard itself is covered by the manual flow in
`phase2.md` §2–§11 against the Vercel URL):

```bash
.venv/bin/python scripts/staging_smoke.py --base-url https://<staging-api-url>
# all steps ok (drop --no-chat only if staging has an LLM key)
```

> Pushing: `phase2/3/4/5.md`, `PHASE2&3.MD`, `frontendbot.md` are gitignored
> local notes — they stay on your disk and never reach Vercel or GitHub.
> `.env*` files are gitignored too; Vercel uses its own env dashboard, never
> repo files. (Alternative: self-host the dashboard with
> `docker/Dockerfile.frontend` + the same three vars as build args.)

## 6. Go live (DNS → prod deploy → verify)

1. Point DNS: `api.` → backend service, `app.` → dashboard. Wait for TLS.
2. Redeploy the backend with **prod** env (fresh `SECRET_KEY`, prod
   `ALLOWED_ORIGINS` = exactly `https://app.yourdomain.com`, prod R2 creds
   if separate). On Vercel, set the three `NEXT_PUBLIC_*` vars to the prod
   URLs and **Redeploy** the production deployment.
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
- **Rollback**: on Vercel, instant-rollback to the previous production
  deployment (or flip `NEXT_PUBLIC_API_BASE_URL` back + redeploy); for data,
  restore the Neon snapshot / latest R2 dump. Keep the SQLite file as
  read-only fallback for 14 days post-launch.

## 8. How all deployments communicate (read this once, deploy everything)

Five pieces, six edges. Every deploy step in §§1–7 is just standing up one
of these edges — if an edge is wrong, the symptom column tells you exactly
which step to revisit.

```
                          ┌─────────────────────────────┐
                          │  Vercel dashboard           │
                          │  app.yourdomain.com         │
                          │  (Next.js, public env only) │
                          └──────────────┬──────────────┘
                                         │ A: HTTPS + Bearer JWT
                                         ▼
                          ┌─────────────────────────────┐
   customer site ──E:────▶│  Backend API                │──B:──▶ Neon Postgres
   <script src=…/widget.js│  api.yourdomain.com         │         + pgvector
   + token in JSON body   │  (stateless, 2 workers)     │
                          └──────────────┬──────────────┘
                                         │ C: presigned URLs only
                                         ▼ (browser PUTs/GETs direct)
                          ┌─────────────────────────────┐
                          │  R2 bucket                  │
                          │  (bytes at rest)            │
                          └─────────────────────────────┘
         D: dashboard/preview deploys pull code from GitHub (never .env*)
```

### Edge A — dashboard → API (your users' everyday traffic)

- **What:** `fetch(${NEXT_PUBLIC_API_BASE_URL}${path})` in
  `BaseBot_UI/src/lib/api-client.ts`, `Authorization: Bearer <jwt>` header
  (stored client-side; 401 → cleared + redirect to login).
- **Deploy knobs:** Vercel env `NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com`
  (**no trailing slash**, baked at build → redeploy after edits);
  backend `ALLOWED_ORIGINS=https://app.yourdomain.com` (restrictive global
  CORS; credentialed). Previews need their own pair (Preview env vars →
  staging API).
- **Fails like:** CORS errors / 401s on every call → mismatched pair (dashboard
  pointing at localhost, or origin missing from `ALLOWED_ORIGINS`).

### Edge B — API → Neon (all state: users, workspaces, docs, chunks, vectors)

- **What:** asyncpg pool (`PG_POOL_*`), pgvector `<=>` KNN, Alembic migrations
  (`0001`, `0002`). The API is stateless — any replica/woker can serve any
  request; there is no sticky session and nothing is cached between requests.
- **Deploy knobs:** pooled `DATABASE_URL` (`?sslmode=require`); keep
  workers × pool-max under Neon's connection limit. Run
  `alembic upgrade head` on every deploy (boot also applies schema).
- **Fails like:** `/health/ready` 503 + `database: error` → URL/pooler wrong;
  `missing table` → migrations never ran.

### Edge C — browsers ↔ R2 (document bytes, never through FastAPI)

- **What:** backend mints short-lived (15 min) presigned URLs
  (`upload-url` → browser `PUT`s bytes → `complete-upload` HEAD-verifies →
  `/train` reads via temp download; `download-url` for reads).
- **Deploy knobs:** `S3_BUCKET/PREFIX/ENDPOINT_URL/REGION/AWS_*` on the API;
  **R2 bucket CORS** must allow `PUT, GET, HEAD` from the exact dashboard
  origin (Vercel Preview origins too while testing). Without `S3_BUCKET` the
  API answers 501 and local-disk flow applies.
- **Fails like:** upload CORS error → R2 CORS missing the dashboard origin;
  `complete-upload` 400 → PUT never happened / URL expired (re-mint).

### Edge D — GitHub → Vercel / PaaS (code deploys, never secrets)

- **What:** pushes build both sides. Vercel reads env from its dashboard;
  the container host reads env from its dashboard. `.env*`, `phase*.md`,
  `data/` never leave your disk (all gitignored).
- **Deploy knobs:** Vercel Root Directory `BaseBot_UI`; backend
  `docker/compose.prod.yml` (no `.env` bake, no DB bind mount).
- **Fails like:** dashboard talks to localhost in prod → env edited without
  **Redeploy** (vars bake at build time).

### Edge E — customer sites → API (the embeddable widget)

- **What:** site owner pastes the snippet from `embed_tokens.py`
  (`<script src="https://api.yourdomain.com/widget.js">` + token).
  The widget POSTs token-in-JSON-body to `/public/chat` and GETs
  `/public/agent/{token}` — **no cookies, no JWT**.
- **Why it needs special CORS:** the global policy only allows the dashboard
  origin, so `PublicSurfaceMiddleware` opens CORS for `/public/*` only
  (reflects origin, strips credentials, adds hardening headers). Real access
  control is per-token `allowed_origins`, enforced in
  `embed_service._check_origin()` — configure it per widget.
- **Deploy knobs:** `APP_PUBLIC_URL=https://api.yourdomain.com` (the snippet
  URL is built from it — wrong value = broken embeds everywhere);
  rate limiter covers `/public/*` (`RATE_LIMIT_ENABLED=true` in prod).
- **Fails like:** widget loads but chat errors → token's `allowed_origins`
  doesn't include the customer domain, or snippet points at the wrong API host.

### Deploy-order cheat sheet (which edge each step stands up)

| Step (§) | Edge stood up | Proves it |
|---|---|---|
| §1 Neon | B (server side) | `alembic upgrade head` → 11 tables |
| §2 R2 | C (storage side) | bucket CORS + lifecycle set |
| §3 backend env+deploy | A (server side), B, E (server side) | `/health/ready` 200 |
| §4 migrate + backfill | B + C (data flowing) | counts match, `backups/` non-empty |
| §5 Vercel + gate + smoke | A, C, D end-to-end | preflight `--strict` 0, smoke all-ok |
| §6 DNS + prod env | A + E on real domains | pilot users sign up, widget embeds |

## 9. Troubleshooting go-live

| Symptom | Fix |
|---|---|
| Service refuses boot (`SECRET_KEY` error) | Real 32+ hex `SECRET_KEY` with `DEBUG=false` |
| `/health/ready` 503 | `DATABASE_URL` wrong/unreachable; check pooler URL + `sslmode=require` |
| Browser upload CORS error | R2 CORS must allow `PUT,GET,HEAD` from the exact dashboard origin |
| `complete-upload` 400 "PUT the bytes first" | Presigned URL expired (15 min) or PUT failed — mint again |
| Chat 401/402 via OpenRouter | Bad key / no credits — top up, key is per-environment |
| Dashboard talks to localhost in prod | Vercel env still has local URLs — set prod `NEXT_PUBLIC_API_BASE_URL` and **Redeploy** (vars bake at build time, edits don't retro-apply). Also check `NEXT_PUBLIC_SITE_URL` matches the custom domain |
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
