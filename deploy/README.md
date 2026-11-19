# BotBase — VPS runbook

Everything needed to run the production stack on one cheap VPS
(Contabo Cloud VPS 4 — 4 vCPU / 8 GB / 100 GB, ≈ €5–6/month) with
PostgreSQL + pgvector, the API, Caddy for TLS, and the dashboard (landing,
pricing, docs, dashboard, hosted chat and the admin panel) on Vercel.
Transactional email goes out through Resend.

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
#    Use a read-only deploy key for the VPS: generate one here, add it on
#    GitHub as a deploy key for the repository, then:
ssh-keygen -t ed25519 -C "botbase-vps" -f /root/.ssh/github_deploy -N ""
cat /root/.ssh/github_deploy.pub        # -> GitHub: repo -> Settings -> Deploy keys
mkdir -p /root/.ssh && cat > /root/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile /root/.ssh/github_deploy
  IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config

git clone git@github.com:XThere7/XvecBot.git /opt/botbase && cd /opt/botbase
git checkout deployChat

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
| `api.<domain>` | the VPS IP | **proxied (orange cloud)** |
| `api-v2.<domain>` | the VPS IP | **proxied (orange cloud)** |
| `www.<domain>` | Vercel (dashboard) | proxied or DNS-only, Vercel issues its own cert |
| `<domain>` (apex) | Vercel | redirect to `www` (set it in Vercel) |
| `app.<domain>` | Vercel | optional redirect to `www` |

One origin serves the whole web app: `ALLOWED_ORIGINS`,
`HOSTED_BASE_URL` and `NEXT_PUBLIC_SITE_URL` must all be exactly
`https://www.<domain>`. `APP_PUBLIC_URL` is the API origin
(`https://api.<domain>`) — different on purpose, and the preflight script
fails if they are the same.

Both API hostnames are deliberately behind Cloudflare. Caddy forwards
`CF-Connecting-IP` as `X-Forwarded-For`, so the per-IP rate limiter still
buckets by the visitor, not the Cloudflare edge. Keep that header mapping in
`deploy/Caddyfile` if the records stay proxied. The current frontend uses
`api-v2.<domain>`; keep `api.<domain>` for compatibility and existing
integrations.

Caddy obtains the TLS certificate automatically (Let's Encrypt, HTTP-01).
Cloudflare should use **Full (strict)** so it validates Caddy's certificate.

## 4. The dashboard on Vercel

Set these as **Production** environment variables in the Vercel project and
redeploy (they are compiled into the browser bundle):

```
NEXT_PUBLIC_API_BASE_URL=https://api-v2.<domain>
NEXT_PUBLIC_APP_NAME=BotBase
NEXT_PUBLIC_SITE_URL=https://www.<domain>
```

Root directory = `BaseBot_UI`, framework = Next.js, build = `npm run build`.
`NEXT_PUBLIC_*` values are compiled into the browser bundle, so changing one
requires a new Vercel deployment.

## 5. Releases

### Frontend — push to GitHub

`deployChat` is the production branch. Vercel is connected to the repository,
so this is the normal release path:

```bash
git add .
git commit -m "feat: ..."
git push origin deployChat
```

Vercel builds `BaseBot_UI` and aliases the successful deployment to
`https://www.<domain>`. Use a feature branch and the generated Preview URL
to test first; merge to `deployChat` only when it is ready.

Only use the Vercel CLI if GitHub auto-deploy is unavailable. Because the
project Root Directory is `BaseBot_UI`, a manual CLI deploy must be run from a
staging directory that contains `BaseBot_UI/` and `.vercel/project.json`.

### Backend — run the VPS release script

```bash
ssh root@<VPS_IP>
cd /opt/botbase
bash deploy/update.sh
```

`update.sh` pulls `deployChat`, snapshots the current backend image, rebuilds,
runs the Alembic migrations with the new code, restarts the containers, waits
for `/health/ready`, and **rolls back automatically** if the new version is
not healthy within 90 seconds. Downtime is 30–90 seconds.

If a change touches both frontend and backend, push first (Vercel deploys the
UI), then run `deploy/update.sh` on the VPS.

### Database changes

Add an Alembic revision under `backend/alembic/versions` as part of the
feature. `deploy/update.sh` runs `alembic upgrade head` before the new API
serves traffic. Take a manual database dump before a destructive migration
until R2 backups are configured.

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
- Watch disk usage: `df -h` (100 GB is comfortable, but images + Postgres
  + logs still grow). Log rotation is configured in the compose file
  (10 MB × 3 per service).

## 10. Cost control

| Item | Cost |
|---|---|
| VPS (Contabo Cloud VPS 4 — 4 vCPU / 8 GB / 100 GB) | ≈ €5–6/month |
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
| Everybody hits 429 | the client IP is not reaching the app: check Caddy forwards `CF-Connecting-IP` as `X-Forwarded-For`, and that uvicorn runs with `--proxy-headers` |
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
