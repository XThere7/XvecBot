# BotBase — VPS runbook

Everything needed to run the production stack on one cheap VPS
(Hetzner CX22 ≈ €4/month) with PostgreSQL + pgvector, the API, Caddy for
TLS, and the dashboard (landing, pricing, docs, dashboard, hosted chat and
the admin panel) on Vercel. Transactional email goes out through Resend.

The long-form version of this (architecture, costs, alternatives, growth
path) is in `production.md` at the repository root.

---

## 1. What runs where

| Service | Container | Published to the internet? |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | no (internal network only) |
| `backend` | built from `docker/Dockerfile.backend` | no — only Caddy reaches it |
| `frontend` | built from `docker/Dockerfile.frontend` | no (behind the `selfhost` profile; normally Vercel serves the dashboard) |
| `proxy` | `caddy:2-alpine` | **yes** — 80/443 only |

Nothing but Caddy is reachable from outside. That is deliberate: it means
nobody can bypass TLS, and the API always sees the real client IP through
`X-Forwarded-For` (which the per-IP rate limiter buckets on).

---

## 2. First boot

```bash
# 1. the box
ssh root@<VPS_IP>
apt update && apt install -y ufw ca-certificates curl git
ufw allow 22,80,443 && ufw enable

# 2. docker
curl -fsSL https://get.docker.com | sh && apt install -y docker-compose-plugin

# 3. the code
git clone <private-repo> /opt/botbase && cd /opt/botbase

# 4. the configuration (secrets live ONLY here, never in git)
cp deploy/env.example /opt/botbase/.env
nano /opt/botbase/.env          # fill in every value
chmod 600 /opt/botbase/.env

# 5. start everything
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml up -d --build
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml ps
```

The first build downloads the embedding and reranker models (~500 MB) and
compiles nothing heavy, so expect 5–15 minutes on a cold cache. The first
`up` also waits for the database to become healthy.

Check the stack:

```bash
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml logs -f backend
curl -fsS http://localhost/health/ready     # through Caddy
```

## 3. DNS

| Record | Points to | Cloudflare mode |
|---|---|---|
| `api.<domain>` | the VPS IP | **DNS-only (grey cloud)** |
| `www.<domain>` | Vercel (dashboard) | proxied or DNS-only, Vercel issues its own cert |
| `<domain>` (apex) | Vercel | redirect to `www` (set it in Vercel) |
| `app.<domain>` | Vercel | optional redirect to `www` |

One origin serves the whole web app: `ALLOWED_ORIGINS`,
`HOSTED_BASE_URL` and `NEXT_PUBLIC_SITE_URL` must all be exactly
`https://www.<domain>`. `APP_PUBLIC_URL` is the API origin
(`https://api.<domain>`) — different on purpose, and the preflight script
fails if they are the same.

> **Keep `api.<domain>` grey.** With Cloudflare's proxy on, Caddy would see
> a Cloudflare edge IP instead of the visitor's, and every visitor would
> share one rate-limit bucket. If you want Cloudflare's proxy, uncomment the
> `CF-Connecting-IP` line in `deploy/Caddyfile`.

Caddy obtains the TLS certificate automatically (Let's Encrypt, HTTP-01).

## 4. The dashboard on Vercel

Set these as **Production** environment variables in the Vercel project and
redeploy (they are compiled into the browser bundle):

```
NEXT_PUBLIC_API_BASE_URL=https://api.<domain>
NEXT_PUBLIC_APP_NAME=BotBase
NEXT_PUBLIC_SITE_URL=https://www.<domain>
```

Root directory = `BaseBot_UI`, framework = Next.js, build = `npm run build`.

## 5. Releases (the manual update cycle)

```bash
cd /opt/botbase
git pull                      # or push from your machine
bash deploy/update.sh
```

`update.sh` snapshots the current image, rebuilds, runs the migrations with
the new code, restarts the containers, waits for `/health/ready`, and
**rolls back automatically** if the new version is not healthy within 90
seconds. Downtime is 30–90 seconds.

The dashboard updates separately: push to GitHub and Vercel redeploys.

## 6. Transactional email (Resend)

Password reset, the welcome mail and admin invites all leave the box over
SMTP. With the default `EMAIL_BACKEND=file` they are written into the
container and never delivered.

1. In Resend: add and verify the sending domain, then add the SPF, DKIM and
   DMARC records it gives you at the DNS provider.
2. In `/opt/botbase/.env`:

```bash
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=<resend api key>
SMTP_SECURITY=starttls
EMAIL_FROM_ADDRESS=no-reply@<domain>
EMAIL_FROM_NAME=BotBase
EMAIL_REPLY_TO=support@<domain>
SUPPORT_EMAIL=support@<domain>
FRONTEND_URL=https://www.<domain>
DOCS_URL=https://www.<domain>/docs
```

3. Restart the API and send yourself a reset mail:

```bash
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  restart backend
```

Resend is send-only: `support@<domain>` must be a real mailbox you read
(a free Zoho or Google mailbox is fine).

## 7. The admin panel

The superadmin role can only be granted from the CLI:

```bash
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -w /app/backend backend python -m app.scripts.create_master_admin \
  --email founder@<domain>
```

Then sign in at `https://www.<domain>/bbx765adm`, enrol TOTP and store the
recovery codes. TOTP seeds are encrypted with `SECRET_KEY` — **rotating
`SECRET_KEY` later invalidates every enrolled authenticator**.

The panel path is obfuscated, not secret. Put it behind Cloudflare Access
(or a WAF rule) for `/bbx765adm*` on both `www` and `api`.

## 8. Backups

```bash
# one backup now
bash deploy/backup.sh

# nightly at 03:17
crontab -e
17 3 * * * cd /opt/botbase && bash deploy/backup.sh >> /var/log/botbase-backup.log 2>&1
```

The dump goes to `<bucket>/backups/pg/<timestamp>.dump`. Configure an R2
lifecycle rule to expire `backups/pg/` after 14 days.

**Restore procedure:** `deploy/restore.md`. Run the practice restore at least
once before you have real customers.

## 9. Monitoring

- `docker compose ps` shows the health of every service.
- The compose healthchecks are what `depends_on` and the load balancer use.
- Add an external uptime check on `https://api.<domain>/health/ready`
  (a free external checker is enough — the box can die without noticing).
- Watch disk usage: `df -h` (a 40 GB disk fills with images + Postgres +
  logs). Log rotation is configured in the compose file (10 MB × 3 per
  service).

## 10. Cost control

| Item | Cost |
|---|---|
| VPS (2 vCPU / 4 GB) | ≈ €4/month |
| PostgreSQL in the same container | €0 |
| Cloudflare R2 (10 GB free, no egress fees) | €0 |
| Cloudflare DNS | €0 |
| OpenRouter free models | €0 (set a $5 spend cap) |
| Domain | ~$10–40/year |
| Resend (transactional email, 3,000/mo free) | $0 |
| Support mailbox | $0–1/month |

## 11. Incident cheat sheet

| Symptom | Action |
|---|---|
| `/health/ready` returns 503 | `compose ps` → `compose logs --tail=100 db backend`; check `DATABASE_URL` and that the `db` container is healthy |
| 502 from the dashboard | the API container is down or not healthy: `compose logs backend` |
| Uploads fail in the browser (CORS) | the R2 bucket CORS must allow `PUT, GET, HEAD` from the dashboard origin |
| Everybody hits 429 | the client IP is not reaching the app: check the DNS record is grey and that uvicorn runs with `--proxy-headers` |
| Chat returns 401/402 | OpenRouter key invalid or out of credit |
| No password-reset mail arrives | `EMAIL_BACKEND` is not `smtp`, or the SMTP credentials are wrong: `compose logs backend` shows the delivery error |
| Password-reset mail lands in spam | SPF/DKIM/DMARC records missing or wrong for the sending domain |
| The pricing page says "We could not load the plans" | the API and the frontend disagree about the plans payload — check `GET /billing/plans` matches `backend/app/core/plan.py` |
| Nobody can sign in to the admin panel | TOTP was enrolled before `SECRET_KEY` was finalised, or the recovery codes were lost |
| Disk > 80% | `docker system prune -a` (images only) · old backups in R2 |
| A bad release | `deploy/update.sh` rolls back automatically; manually: `docker tag botbase-backend:prev <image>` + `compose up -d --no-deps backend` |
| Need a restore | `deploy/restore.md` |

## 12. Local development against the same stack

```bash
# Postgres + pgvector on your own machine (no Docker needed)
bash scripts/dev_postgres.sh start
export DATABASE_URL="postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase"

# the full verification gate (SQLite suite, Postgres suite, migrations, E2E)
bash scripts/verify_postgres.sh
```
