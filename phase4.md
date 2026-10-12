# Phase 4 — Deploy Hardening: Runtime User, Rate Limiting, Backups, Logging

Execution record for the production-readiness work completed **2026-10-12**.
Goal: make the containers safe to run (no root-owned host data), add abuse
mitigation that can't hurt local dev, ship a real backup primitive, and make
log verbosity tunable. Same design rule as Phases 2–3: production behavior
arrives **behind env**; the local default never moves.

---

## 1. What was built

### 1.1 Root-owned data fix (`docker/Dockerfile.backend`, `docker-compose.yml`, `compose.prod.yml`)

Root cause of the 2026-10-11 incident (a `rag-backend` container zeroed the
developer's `data/rag.db` and left root-owned files): the image ran as root
with a `../data:/app/data` bind mount, so every file the container created
belonged to root on the host.

| File | Change |
|---|---|
| `docker/Dockerfile.backend` | `chmod -R a+rwX data .hf-cache`; new non-root `appuser` (uid 1000), owns `/app/data` + `/app/.hf-cache`; `USER appuser` |
| `docker/docker-compose.yml` (dev) | `user: "${UID:-1000}:${GID:-1000}"` on backend — bind-mounted files keep host identity |
| `docker/compose.prod.yml` | Runs as image `appuser` by default; **removed** the `hf-cache` named volume (it would hide the build-time-baked weights and force a re-download); removed obsolete `version:` key; added `RATE_LIMIT_ENABLED=true`, `RATE_LIMIT_PER_MINUTE`, `LOG_LEVEL` |

Both composes validate (`docker compose … config`, exit 0).

### 1.2 Rate limiting (`backend/app/core/rate_limit.py`, `main.py`, `config.py`)

- `RateLimitMiddleware`: in-memory fixed-window (60 s), per-IP buckets,
  **scoped to `/auth/*` + `/public/*`** (login/register brute force, widget
  abuse). Dashboard JWT routes and `/health*` are never throttled.
- Env-gated: `RATE_LIMIT_ENABLED` default **false** (dev/tests untouched);
  prod compose sets `true`, `RATE_LIMIT_PER_MINUTE` default 60.
- 429 responses carry `Retry-After`; allowed responses carry
  `X-RateLimit-Limit`. Settings re-read per request so tests toggle without
  rebuilding the app. Wired outermost in `main.py` (after
  `PublicSurfaceMiddleware`).
- Multi-replica caveat (documented in code): counters are per-process memory —
  correct for abuse mitigation, not strict global quotas (that needs Redis).

### 1.3 Logging (`backend/app/core/logging.py`, `config.py`)

Production already logs JSON to stdout (what PaaS drains collect); this phase
adds a `LOG_LEVEL` override (`DEBUG/INFO/WARNING/ERROR`, empty = derived from
`DEBUG`). Prod compose sets `INFO`.

### 1.4 Backups (`scripts/backup_postgres_to_r2.py`)

Nightly-backup primitive, database bytes → versioned R2 bucket:

- `--dry-run` — prints DB kind, size/pg_dump availability, storage target.
- `--pg` — `pg_dump --format=custom --no-owner` → `backups/pg/<ts>.dump`
  (needs `pg_dump` + S3 configured; aborts loudly otherwise).
- `--sqlite` — local file → `backups/sqlite/<ts>.db` (dev/transition use).
- R2 bucket versioning + lifecycle expiry configured once in the Cloudflare
  dashboard; Neon PITR is the point-in-time story, these dumps are the
  portable second copy. Suggested cron is in the script docstring.
- Reuses the Phase 2 `S3Backend` (no new storage code).

### 1.5 `.env.example`

Documents `RATE_LIMIT_ENABLED`, `RATE_LIMIT_PER_MINUTE`, `LOG_LEVEL`.

---

## 2. Tests + verification results (2026-10-12)

| Check | Result |
|---|---|
| New `test_rate_limit.py` (off-by-default burst passes; enabled limit-2 → `201,201,429` + `Retry-After`; `/health` unthrottled when enabled) | **2/2 PASS** |
| Full suite | **21 passed, 4 skipped** (HF downloads), **1 failed — pre-existing** LangGraph `'citations' state key` (identical on clean tree) |
| Dev-DB pollution check (23 users / 20 workspaces / 15 upload dirs before **and** after) | **PASS — no restore needed** |
| Backup `--dry-run` (sqlite, real 2 MB file reported) | PASS |
| Backup `--sqlite` → moto-S3 roundtrip (2,084,864 bytes stored + listed) | PASS |
| Both compose files `config` validation | PASS (exit 0) |
| `py_compile` on all touched files | PASS |

---

## 3. Operational notes

1. **Rotate `OPENROUTER_API_KEY`** — still live in untracked `.env`.
2. `USER appuser` changes container runtime identity: if any host bind-mount
   file is not world-readable/writable, `chown`/`chmod` it on the host or set
   `UID:GID` in dev compose (default 1000:1000 already matches `appuser`).
3. Rate limiting is per-process: with `UVICORN_WORKERS=2`, effective global
   threshold is ~2× the configured value. Fine for abuse mitigation.
4. Durable dev-DB backup: `~/.xvec-backups/rag.db.phase2-start-2026-10-11`.
5. Commit for this phase: `Phase 4: …` on the current branch (local commit,
   unpushed unless you ask).
