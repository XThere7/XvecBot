"""
Stage 1 E2E — full customer journey against a REAL PostgreSQL + pgvector backend.

  auth -> workspace -> upload -> train -> RAG chat (answer + sources)
  -> multi-turn -> conversations -> embed token -> public/widget API
  -> hosted origin checks -> QR -> legacy /api/v1 API -> developer keys
  -> workspace deletion -> prove zero leftover workspace rows (in Postgres)
     and zero leftover files (on disk).

Field names differ per contract on purpose:
  agent/public chat -> "sources"      legacy /api/v1/query -> "citations"

Exits non-zero if any assertion fails.
"""
import asyncio
import io
import json
import os
import sys
import time
import uuid

import asyncpg
import httpx

API = os.environ.get("E2E_API", "http://127.0.0.1:8000")
DSN = os.environ.get(
    "E2E_DSN",
    "postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase_e2e",
)
LEGACY_KEY = os.environ.get("E2E_LEGACY_KEY", "e2e-legacy-key")
HOSTED_ORIGIN = os.environ.get("E2E_HOSTED_ORIGIN", "http://localhost:3000")
UPLOAD_DIR = os.environ.get("E2E_UPLOAD_DIR", "/tmp/opencode/stage1/uploads")

PASSED, FAILED, KNOWN = [], [], []


def check(cond, label, extra=""):
    if cond:
        PASSED.append(label)
        print(f"PASS  {label}", flush=True)
    else:
        FAILED.append(f"{label} {extra}".strip())
        print(f"FAIL  {label} {extra}".strip(), flush=True)


def known(label, extra=""):
    KNOWN.append(f"{label} {extra}".strip())
    print(f"KNOWN {label} {extra}".strip(), flush=True)


def note(label, extra=""):
    """Informational line that is neither a pass nor a failure."""
    print(f"NOTE  {label} {extra}".strip(), flush=True)


def make_pdf(text: str) -> bytes:
    """A tiny real PDF (so the legacy upload route accepts it)."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text[:90])
    out = doc.tobytes()
    doc.close()
    return out


async def wait_status(client, headers, ws, doc, want=("ready", "failed"), timeout=240):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = await client.get(f"/workspaces/{ws}/documents/{doc}/status", headers=headers)
        if r.status_code != 200:
            last = f"http {r.status_code}: {r.text[:200]}"
        else:
            last = r.json().get("status")
            if last in want:
                return last
        await asyncio.sleep(2)
    return last


async def main():
    tag = uuid.uuid4().hex[:10]
    email = f"stage1-{tag}@example.com"
    password = "StrongPass123!"
    restricted_origin = "http://shop.example.com"

    async with httpx.AsyncClient(base_url=API, timeout=180) as c:
        # ── health ─────────────────────────────────────────────────────────
        r = await c.get("/health/ready")
        check(r.status_code == 200 and r.json().get("database") == "ok",
              "readiness reports the database is ok", r.text[:200])

        # ── auth ───────────────────────────────────────────────────────────
        r = await c.post("/auth/register", json={"email": email, "password": password})
        check(r.status_code == 201, "register returns 201", r.text[:200])
        token = r.json()["access_token"]
        user_id = r.json()["user_id"]
        headers = {"Authorization": f"Bearer {token}"}

        r = await c.post("/auth/register", json={"email": email, "password": password})
        check(r.status_code in (400, 409), "duplicate registration is rejected", r.text[:200])

        r = await c.post("/auth/login", json={"email": email, "password": "WrongPass123"})
        check(r.status_code == 401, "wrong password is rejected", r.text[:200])

        r = await c.post("/auth/login", json={"email": email, "password": password})
        check(r.status_code == 200 and "access_token" in r.json(), "login returns a token")
        check(r.json()["user_id"] == user_id, "login returns the same user")

        # ── registration trial ─────────────────────────────────────────────
        r = await c.get("/auth/me", headers=headers)
        me = r.json()
        check(
            r.status_code == 200
            and me["plan"]["base"] == "free"
            and me["plan"]["effective"] == "trial"
            and me["plan"]["is_trial"] is True,
            "new account starts on a trial with a Free base plan",
            r.text[:200],
        )
        check(
            me["plan"]["days_remaining"] in (20, 21)
            and me["limits"]["agents"] is None
            and me["limits"]["chat_messages"] is None,
            "trial grants Pro-equivalent limits for 21 days",
            json.dumps(me.get("plan")),
        )

        # ── workspace ──────────────────────────────────────────────────────
        r = await c.post(
            "/workspaces", json={"name": "Stage 1 QA", "description": "postgres"}, headers=headers
        )
        check(r.status_code in (200, 201), "workspace created", r.text[:200])
        ws = r.json()["id"]

        # ── public plan catalogue ──────────────────────────────────────────
        r = await c.get("/plans")
        catalogue = r.json()
        plans = {p["id"]: p for p in (catalogue.get("plans") or [])}
        check(r.status_code == 200 and set(plans) == {"free", "standard", "pro"},
              "public catalogue exposes exactly three plans", r.text[:200])
        check(
            plans["free"]["price_tzs"] == 0
            and plans["standard"]["price_tzs"] == 7_800
            and plans["pro"]["price_tzs"] == 15_800,
            "plan prices are Free 0, Standard 7,800 and Pro 15,800 TZS",
        )
        free_limits = plans["free"]["limits"]
        check(
            free_limits["agents"] == 1
            and free_limits["documents"] == 5
            and free_limits["pages_indexed"] == 50
            and free_limits["website_sources"] == 1
            and free_limits["website_refresh"] == "manual"
            and free_limits["api_keys"] == 0
            and free_limits["chat_messages"] == 100
            and free_limits["embed_tokens"] == 1,
            "Free limits match the approved launch strategy",
            json.dumps(free_limits),
        )
        standard_limits = plans["standard"]["limits"]
        check(
            standard_limits["agents"] == 5
            and standard_limits["documents"] == 50
            and standard_limits["pages_indexed"] == 500
            and standard_limits["website_sources"] == 5
            and standard_limits["website_refresh"] == "weekly"
            and standard_limits["api_keys"] == 3
            and standard_limits["chat_messages"] == 5_000
            and standard_limits["embed_tokens"] == 5,
            "Standard limits match the approved launch strategy",
            json.dumps(standard_limits),
        )
        pro_limits = plans["pro"]["limits"]
        check(
            all(
                pro_limits[key] is None
                for key in (
                    "agents",
                    "documents",
                    "pages_indexed",
                    "website_sources",
                    "api_keys",
                    "chat_messages",
                    "embed_tokens",
                )
            )
            and pro_limits["website_refresh"] == "daily",
            "Pro limits are unlimited with daily refresh",
            json.dumps(pro_limits),
        )
        check(catalogue["trial"]["duration_days"] == 21,
              "public catalogue advertises the 21-day trial")
        check(catalogue["payments_configured"] is False,
              "public catalogue reports payments are not configured")

        # ── trial billing view, then expire the trial for Free gates ───────
        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        billing = r.json()
        check(
            r.status_code == 200
            and billing["plan"]["id"] == "pro"
            and billing["is_trial"] is True
            and billing["base_plan"] == "free",
            "trial workspace bills as Pro with a Free base",
            r.text[:200],
        )
        check(bool(billing["usage"]["chat_messages"]["resets_at"]),
              "billing exposes the monthly chat reset date")

        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                "UPDATE users SET trial_ends_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = $1",
                user_id,
            )
        finally:
            await conn.close()

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        billing = r.json()
        check(
            r.status_code == 200
            and billing["plan"]["id"] == "free"
            and billing["is_trial"] is False,
            "expired trial drops the account to Free",
            r.text[:200],
        )
        check(billing["payments_configured"] is False,
              "billing reports payments are not configured")

        # Developer API is a Standard/Pro entitlement and is locked on Free.
        r = await c.post(
            f"/workspaces/{ws}/api-keys", json={"name": "locked key"}, headers=headers
        )
        check(r.status_code == 403, "Free cannot create developer API keys", r.text[:200])
        detail = (r.json().get("detail") or {})
        check(
            detail.get("code") == "plan_limit_reached"
            and detail.get("resource") == "api_keys"
            and detail.get("limit") == 0,
            "locked developer key returns a structured plan error",
            r.text[:200],
        )

        # The Free gates above are proven. Move this disposable workspace to
        # Pro before the rest of the journey so two embed tokens and the
        # developer API are exercised under the paid entitlement.
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                "UPDATE workspaces SET plan = 'pro', plan_started_at = now()::text "
                "WHERE id = $1",
                ws,
            )
        finally:
            await conn.close()

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        check(
            r.status_code == 200 and r.json()["plan"]["id"] == "pro",
            "operator upgrade to Pro is reflected in billing",
            r.text[:200],
        )

        r = await c.get("/workspaces", headers=headers)
        check(any(w["id"] == ws for w in r.json()), "workspace appears in the list")

        r = await c.get(f"/workspaces/{ws}", headers=headers)
        check(r.status_code == 200, "workspace can be fetched")

        r = await c.put(f"/workspaces/{ws}", json={"name": "Stage 1 QA renamed"}, headers=headers)
        check(r.status_code == 200, "workspace can be renamed", r.text[:200])

        # ── upload + training ──────────────────────────────────────────────
        body = (
            b"BotBase Stage 1 hosting test document.\n"
            b"Refund policy: refunds are issued within 14 days of purchase.\n"
            b"Support hours: Monday to Friday, 09:00 to 17:00 EAT.\n"
            b"Order tracking: parcels leave the warehouse within 48 hours.\n"
        )
        r = await c.post(
            f"/workspaces/{ws}/documents",
            files={"file": ("policy.txt", io.BytesIO(body), "text/plain")},
            headers=headers,
        )
        check(r.status_code in (200, 201), "document uploaded", r.text[:200])
        doc = r.json()["id"]

        r = await c.post(f"/workspaces/{ws}/documents/{doc}/train", headers=headers)
        check(r.status_code in (200, 202), "training accepted", r.text[:200])

        status = await wait_status(c, headers, ws, doc)
        check(status == "ready", "document trained to ready", f"status={status}")

        r = await c.get(f"/workspaces/{ws}/documents", headers=headers)
        check(any(d["id"] == doc for d in r.json()), "document appears in the list")

        # ── the vectors really are in pgvector ─────────────────────────────
        conn = await asyncpg.connect(DSN)
        try:
            from pgvector.asyncpg import register_vector

            await register_vector(conn)
            n_chunks = await conn.fetchval("SELECT count(*) FROM chunks")
            n_vec = await conn.fetchval("SELECT count(*) FROM chunk_embeddings")
            col_type = await conn.fetchval(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name='chunk_embeddings' AND column_name='embedding'"
            )
            knn = await conn.fetch(
                "SELECT chunk_id FROM chunk_embeddings "
                "ORDER BY embedding <=> $1::vector LIMIT 3",
                [0.1] * 384,
            )
            check(n_chunks > 0, "chunks stored in postgres", f"chunks={n_chunks}")
            check(n_vec > 0, "embeddings stored in postgres", f"embeddings={n_vec}")
            check(col_type == "vector", "embedding column is pgvector type", f"type={col_type}")
            check(len(knn) > 0, "pgvector KNN query returns neighbours")
        finally:
            await conn.close()

        # ── agent + RAG chat ───────────────────────────────────────────────
        r = await c.post(
            f"/workspaces/{ws}/agents",
            json={
                "name": "Support Bot",
                "description": "answers policy questions",
                "system_prompt": "Answer using the knowledge base. Be brief.",
                "welcome_message": "Hi! Ask me about refunds or support hours.",
            },
            headers=headers,
        )
        check(r.status_code in (200, 201), "agent created", r.text[:200])
        agent = r.json()["id"]

        r = await c.post(
            f"/workspaces/{ws}/agents/{agent}/chat",
            json={"message": "What is the refund window?"},
            headers=headers,
        )
        check(r.status_code == 200, "dashboard chat accepted", r.text[:200])
        chat = r.json()
        answer = (chat.get("answer") or "").strip()
        check(bool(answer), "chat returned an answer", f"keys={list(chat)}")
        sources = chat.get("sources") or []
        check(len(sources) > 0, "chat returned sources", f"n={len(sources)}")
        conv_id = chat.get("conversation_id")
        check(bool(conv_id), "chat returned a conversation id")

        r = await c.post(
            f"/workspaces/{ws}/agents/{agent}/chat",
            json={"message": "And when are you open?", "conversation_id": conv_id},
            headers=headers,
        )
        check(r.status_code == 200, "multi-turn chat accepted", r.text[:200])
        check(r.json().get("conversation_id") == conv_id, "conversation id is preserved")

        r = await c.get(f"/workspaces/{ws}/agents/{agent}/conversations", headers=headers)
        convs = r.json()
        check(len(convs) >= 1, "conversation list is populated", f"n={len(convs)}")

        r = await c.get(
            f"/workspaces/{ws}/agents/{agent}/conversations/{conv_id}", headers=headers
        )
        check(r.status_code == 200, "conversation thread loads", r.text[:200])
        msgs = r.json().get("messages") or []
        check(len(msgs) >= 2, "thread contains both turns", f"n={len(msgs)}")

        # workspace-level chat route (separate contract)
        r = await c.post(
            f"/workspaces/{ws}/chat",
            json={"message": "What are the support hours?"},
            headers=headers,
        )
        check(r.status_code == 200, "workspace chat works", r.text[:300])

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        usage = r.json().get("usage") or {}
        check(
            (usage.get("chat_messages") or {}).get("used", 0) >= 3,
            "account chat usage counts every chat surface",
            json.dumps(usage.get("chat_messages")),
        )
        check(
            (usage.get("documents") or {}).get("used") == 1
            and (usage.get("agents") or {}).get("used") == 1,
            "billing usage reports documents and agents",
            json.dumps(usage),
        )

        # ── embed token + hosted page links ────────────────────────────────
        r = await c.post(
            f"/workspaces/{ws}/agents/{agent}/tokens",
            json={"label": "Stage 1 widget", "allowed_origins": None},
            headers=headers,
        )
        check(r.status_code in (200, 201), "embed token created", r.text[:200])
        tok_body = r.json()
        tok = tok_body.get("token")

        r = await c.post(
            f"/workspaces/{ws}/agents/{agent}/tokens",
            json={"label": "Shop widget", "allowed_origins": [restricted_origin]},
            headers=headers,
        )
        check(r.status_code in (200, 201), "origin-restricted embed token created", r.text[:200])
        restricted_tok = r.json().get("token")

        r = await c.get(
            f"/workspaces/{ws}/agents/{agent}/tokens/{tok_body['id']}/snippet", headers=headers
        )
        check(r.status_code == 200, "embed snippet fetched", r.text[:200])
        snippet = r.json()
        check(tok in (snippet.get("snippet") or ""), "snippet embeds the token")
        hosted_url = snippet.get("hosted_url") or ""
        check("/chat/" in hosted_url, "snippet exposes a hosted chat url", hosted_url)

        # ── public / widget surface ────────────────────────────────────────
        r = await c.get(f"/public/agent/{tok}")
        check(r.status_code == 200, "public agent info returns 200", r.text[:200])
        info = r.json()
        for leaked in ("workspace_id", "owner_id", "system_prompt"):
            check(leaked not in info, f"public info hides {leaked}")

        r = await c.post(
            "/public/chat",
            json={"token": tok, "message": "What is the refund window?"},
            headers={"Origin": HOSTED_ORIGIN},
        )
        check(r.status_code == 200, "public chat from the hosted origin works", r.text[:300])
        pub = r.json()
        check(bool((pub.get("answer") or "").strip()), "public chat returned an answer")
        check(len(pub.get("sources") or []) > 0, "public chat returned sources")

        r = await c.post(
            "/public/chat",
            json={"token": restricted_tok, "message": "hello"},
            headers={"Origin": "http://evil.example.com"},
        )
        check(r.status_code == 403, "restricted token refuses an unrelated origin", r.text[:200])

        r = await c.post(
            "/public/chat",
            json={"token": restricted_tok, "message": "hello"},
            headers={"Origin": restricted_origin},
        )
        check(r.status_code == 200, "restricted token accepts its own origin", r.text[:200])

        r = await c.post(
            "/public/chat",
            json={"token": "not-a-real-token", "message": "hello"},
            headers={"Origin": HOSTED_ORIGIN},
        )
        check(r.status_code in (401, 404), "public chat rejects an unknown token", r.text[:200])

        r = await c.get(f"/public/qr/{tok}")
        check(r.status_code == 200 and r.headers.get("content-type", "").startswith("image/png"),
              "QR endpoint returns a PNG", f"{r.status_code} {r.headers.get('content-type')}")

        # ── legacy /api/v1 surface (API_KEY) ───────────────────────────────
        legacy = {"X-API-Key": LEGACY_KEY}
        r = await c.get("/api/v1/documents", headers=legacy)
        check(r.status_code == 200, "legacy /api/v1/documents works", r.text[:200])
        r = await c.get("/api/v1/documents/", headers=legacy)
        check(r.status_code == 200, "legacy /api/v1/documents/ (slash) works", r.text[:200])
        r = await c.get("/api/v1/documents", headers={"X-API-Key": "wrong-key"})
        check(r.status_code in (401, 403), "legacy API rejects a bad key", r.text[:200])

        pdf = make_pdf("Legacy upload body: refunds within 14 days.")
        r = await c.post(
            "/api/v1/documents/upload",
            files={"file": ("legacy.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=legacy,
        )
        check(r.status_code in (200, 201), "legacy upload works", r.text[:200])
        legacy_doc = (r.json() or {}).get("id") or (r.json() or {}).get("document_id")
        check(bool(legacy_doc), "legacy upload returned a document id", r.text[:200])

        r = await c.post(
            "/api/v1/query/", json={"question": "What is the refund window?"}, headers=legacy
        )
        check(r.status_code == 200, "legacy query works", r.text[:300])
        legacy_body = r.json()
        check(len(legacy_body.get("citations") or []) > 0, "legacy query returned citations")
        check(bool(legacy_body.get("conversation_id")), "legacy query returned a conversation id")

        # ── developer API keys ─────────────────────────────────────────────
        # Operator upgrade: developer access is Pro-only, and the public API
        # deliberately has no self-service paid upgrade while payments are not
        # configured. Simulate the operator moving this workspace to Pro.
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                "UPDATE workspaces SET plan = 'pro', plan_started_at = now()::text "
                "WHERE id = $1",
                ws,
            )
        finally:
            await conn.close()

        r = await c.get(f"/workspaces/{ws}/billing", headers=headers)
        check(r.status_code == 200 and r.json()["plan"]["id"] == "pro",
              "operator upgrade to Pro is reflected in billing", r.text[:200])

        r = await c.post(
            f"/workspaces/{ws}/api-keys", json={"name": "Stage 1 key"}, headers=headers
        )
        check(r.status_code in (200, 201), "developer key created", r.text[:200])
        key_body = r.json()
        full_key = key_body.get("key")
        check(bool(full_key) and full_key.startswith("sk-botbase-"), "developer key returned once")
        check(key_body.get("key_prefix"), "developer key returns a prefix")

        r = await c.get(f"/workspaces/{ws}/api-keys", headers=headers)
        keys = r.json()
        check(len(keys) == 1, "developer key listed")
        check(all("key" not in k for k in keys), "list never exposes the plaintext key")

        dev = {"X-API-Key": full_key}
        r = await c.get("/api/v1/agents", headers=dev)
        check(r.status_code == 200, "developer key authenticates", r.text[:200])
        check(r.json()["workspace_id"] == ws, "developer key is workspace scoped")

        r = await c.post(
            "/api/v1/chat",
            json={"agent_id": agent, "message": "What is the refund window?"},
            headers=dev,
        )
        check(r.status_code == 200, "developer chat works", r.text[:300])
        check(bool((r.json().get("answer") or "").strip()), "developer chat returned an answer")

        r = await c.put(
            f"/workspaces/{ws}/api-keys/{key_body['id']}",
            json={"allowed_agents": [agent]},
            headers=headers,
        )
        check(r.status_code == 200, "developer key restricted to one agent", r.text[:200])

        r = await c.put(
            f"/workspaces/{ws}/api-keys/{key_body['id']}",
            json={"is_active": 0},
            headers=headers,
        )
        check(r.status_code == 200, "developer key revoked via update", r.text[:200])
        r = await c.get("/api/v1/agents", headers=dev)
        check(r.status_code == 401, "revoked developer key is rejected immediately", r.text[:200])

        # ── deletion + zero leftovers ──────────────────────────────────────
        r = await c.delete(f"/workspaces/{ws}", headers=headers)
        check(r.status_code in (200, 204), "workspace deleted", r.text[:200])

        # The legacy /api/v1 upload is a global artifact (not workspace-scoped),
        # so it is removed through its own endpoint.
        if legacy_doc:
            r = await c.delete(f"/api/v1/documents/{legacy_doc}", headers=legacy)
            check(r.status_code in (200, 204), "legacy document deleted", r.text[:200])

        conn = await asyncpg.connect(DSN)
        try:
            leftovers = {}
            for table in (
                "workspaces",
                "workspace_documents",
                "documents",
                "chunks",
                "chunk_embeddings",
                "agents",
                "agent_embed_tokens",
                "developer_api_keys",
                "usage_events",
                "website_sync_jobs",
                "website_pages",
                "website_sources",
            ):
                leftovers[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
            total = sum(leftovers.values())
            check(total == 0, "postgres has zero leftover workspace rows", json.dumps(leftovers))

            orphan_convs = await conn.fetchval(
                "SELECT count(*) FROM conversations WHERE agent_id IS NOT NULL"
            )
            check(orphan_convs == 0, "no agent conversation survived the delete", f"n={orphan_convs}")

            # DATA-02 (Stage 2): a transcript that quotes workspace data is
            # linked to the workspace and must die with it.
            linked_survivors = await conn.fetchval(
                "SELECT count(*) FROM conversations WHERE workspace_id = $1", ws
            )
            check(
                linked_survivors == 0,
                "no workspace-linked conversation survived the delete",
                f"n={linked_survivors}",
            )

            legacy_convs = await conn.fetchval(
                "SELECT count(*) FROM conversations "
                "WHERE agent_id IS NULL AND workspace_id IS NULL"
            )
            if legacy_convs:
                # Expected: this E2E's legacy query quoted a GLOBAL legacy
                # upload (not workspace data), so there is no workspace to
                # attribute the transcript to.
                note(
                    "legacy /api/v1/query transcript of a global legacy document",
                    f"n={legacy_convs} (no workspace owner is correct here)",
                )
        finally:
            await conn.close()

    files = []
    for root, _dirs, names in os.walk(UPLOAD_DIR):
        for n in names:
            files.append(os.path.join(root, n))
    check(not files, "no leftover files on disk", f"n={len(files)}")

    print(f"\n=== STAGE1 E2E: {len(PASSED)} passed, {len(FAILED)} failed, {len(KNOWN)} known ===")
    if KNOWN:
        for k in KNOWN:
            print("  KNOWN:", k)
    if FAILED:
        for f in FAILED:
            print("  FAILED:", f)
        sys.exit(1)
    print("STAGE1_E2E_RESULT=PASS")


if __name__ == "__main__":
    asyncio.run(main())
