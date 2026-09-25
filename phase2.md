# Phase 2 — Multi-Tenant SaaS RAG: Manual Test Guide

Complete walkthrough of every Phase 2 feature, from registration through workspace chat.
Follow top to bottom — each step builds on the previous one.

---

## 0. Prerequisites & Setup

### 0.1 Environment

| Item | Value |
|---|---|
| Python | **3.13** (do not use 3.14 — `pydantic-core` fails to build) |
| Virtualenv | `.venv` at **project root** |
| Server URL | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| DB file | `data/rag.db` |
| Uploads | `uploads/{workspace_id}/` |

### 0.2 Start the backend

```bash
cd /home/jteckz7/Xvec-chat/backend
../.venv/bin/uvicorn app.main:app --port 8000
```

Wait for this in the log:

```
Application startup complete
```

> First start takes ~15 s (embedding model warm-up). If it warns
> `Embedding warmup skipped`, the server still works — embeddings lazy-load on first use.

### 0.3 Configure the LLM key (required only for chat)

Chat needs an OpenRouter key. Without it, every chat call returns **500**.

```bash
cp .env.example .env
# then edit .env and set:
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Get a key: <https://openrouter.ai/keys>
Restart the server after editing `.env`.

**Check if the LLM is working:**

```bash
curl -s http://localhost:8000/api/v1/query/llm/status -H "X-API-Key: dev-key"
```

Expected: `{"provider":"openrouter","ok":true,...}`
If `"ok":false`, the error field tells you exactly what is missing.

---

## 1. Health Check (confirm server is alive)

```bash
curl -s http://localhost:8000/health
```

**Expected**
```json
{"status":"ok","app":"production-rag","version":"1.0.0","timestamp":"...","uptime_seconds":12.4}
```

```bash
curl -s http://localhost:8000/health/ready
```

**Expected:** `{"status":"ready","database":"ok",...}`

If `"status":"not_ready"` → database unreachable, check `data/rag.db` permissions.

---

## 2. Authentication

### 2.1 Set up shell variables

```bash
B=http://localhost:8000
PY=/home/jteckz7/Xvec-chat/.venv/bin/python
EMAIL="you@example.com"
```

### 2.2 Register

```bash
curl -s -X POST $B/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"password1"}'
```

**Expected (201)**
```json
{"access_token":"eyJhbGciOiJIUzI1NiIs...","token_type":"bearer","user_id":"9cacdfbc-..."}
```

Save the token:

```bash
TOKEN=$(curl -s -X POST $B/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"password1"}' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

AUTH="Authorization: Bearer $TOKEN"
echo "$TOKEN" | cut -c1-30   # sanity check
```

> Password must be **≥ 8 characters** → otherwise `422`.

### 2.3 Duplicate email is rejected

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"password1"}'
```

**Expected:** `HTTP 400` + `{"detail":"Email already registered"}`

### 2.4 Login

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"password1"}'
```

**Expected:** `HTTP 200` + access token JSON (same shape as register)

### 2.5 Wrong password is rejected

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"wrongpass1"}'
```

**Expected:** `HTTP 401` + `{"detail":"Invalid credentials"}`

### 2.6 Unknown email is rejected

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@example.com","password":"password1"}'
```

**Expected:** `401` (deliberately identical to wrong password — no user enumeration)

### 2.7 Auth is required on tenant endpoints

```bash
curl -s -o /dev/null -w "%{http_code}\n" $B/workspaces
```

**Expected:** `401` — not a list. Any missing/invalid token returns 401.

---

## 3. Workspaces CRUD

### 3.1 Create

```bash
WS=$(curl -s -X POST $B/workspaces \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"EASTTECH Support","description":"Customer support bot","system_prompt":"You are EASTECH'"'"'s support bot. Answer only from the documents."}' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "workspace id: $WS"
```

**Expected (201)**
```json
{
  "id": "e51d0087-...",
  "name": "EASTTECH Support",
  "description": "Customer support bot",
  "system_prompt": "You are EASTTECH's support bot. Answer only from the documents.",
  "owner_id": "9cacdfbc-...",
  "created_at": "2026-09-23T22:06:27.471144+00:00"
}
```

> `owner_id` always comes from the token, never from the request body.

### 3.2 Create with defaults (optional fields omitted)

```bash
curl -s -X POST $B/workspaces -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"name":"Minimal"}'
```

**Expected:** `system_prompt` = `"You are a helpful assistant."`, `description` = `null`

### 3.3 List (only your own)

```bash
curl -s $B/workspaces -H "$AUTH" | $PY -m json.tool
```

**Expected:** array containing only workspaces you own.

### 3.4 Get one

```bash
curl -s $B/workspaces/$WS -H "$AUTH" | $PY -m json.tool
```

**Expected:** the full workspace object.

### 3.5 Update (partial — only fields you send change)

```bash
curl -s -X PUT $B/workspaces/$WS -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"system_prompt":"New prompt"}'
```

**Expected:** `system_prompt` changed, `name` and `description` **unchanged**.

### 3.6 Ownership isolation (critical security test)

Register a second user and try to touch the first user's workspace:

```bash
EMAIL2="other@example.com"
AUTH2="Authorization: Bearer $(curl -s -X POST $B/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"'"$EMAIL2"'","password":"password1"}' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['access_token'])")"

curl -s -o /dev/null -w "GET    -> %{http_code}\n" $B/workspaces/$WS -H "$AUTH2"
curl -s -o /dev/null -w "PUT    -> %{http_code}\n" -X PUT $B/workspaces/$WS -H "$AUTH2" \
  -H "Content-Type: application/json" -d '{"name":"Hacked"}'
curl -s -o /dev/null -w "DELETE -> %{http_code}\n" -X DELETE $B/workspaces/$WS -H "$AUTH2"
```

**Expected:** `404`, `404`, `404` — never `403`.
> `404` (not `403`) is intentional: it does not reveal that the workspace exists.

Verify the workspace was **not** modified:

```bash
curl -s $B/workspaces/$WS -H "$AUTH" | $PY -c "import sys,json;print(json.load(sys.stdin)['name'])"
```

**Expected:** `EASTTECH Support` (unchanged)

---

## 4. Document Upload

### 4.1 Upload a PDF

```bash
DOC=$(curl -s -X POST $B/workspaces/$WS/documents -H "$AUTH" \
  -F "file=@/home/jteckz7/Xvec-chat/tcp-port-scanner-guide.pdf" \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "doc id: $DOC"
```

**Expected (201)**
```json
{
  "id": "f7456dea-...",
  "workspace_id": "e51d0087-...",
  "filename": "tcp-port-scanner-guide.pdf",
  "file_path": "/home/jteckz7/Xvec-chat/uploads/e51d0087-.../f7456dea-..._tcp-port-scanner-guide.pdf",
  "file_type": "pdf",
  "size_bytes": 263868,
  "status": "uploaded",
  "chunk_count": 0,
  "created_at": "..."
}
```

`status` is `uploaded` — nothing is trained yet.

### 4.2 Upload TXT and DOCX

```bash
printf 'ZEBRAFISH telemetry handles alpha constellation routing. ' > /tmp/test.txt
curl -s -X POST $B/workspaces/$WS/documents -H "$AUTH" \
  -F "file=@/tmp/test.txt;filename=notes.txt" | $PY -m json.tool
```

```bash
/home/jteckz7/Xvec-chat/.venv/bin/python -c "
import docx
d = docx.Document()
for i in range(10):
    d.add_paragraph(f'Paragraph {i}: workspace retrieval and citations. ' * 4)
d.save('/tmp/test.docx')
print('docx created')"
curl -s -X POST $B/workspaces/$WS/documents -H "$AUTH" \
  -F "file=@/tmp/test.docx" | $PY -c "import sys,json;print(json.load(sys.stdin)['file_type'])"
```

**Expected:** `txt` and `docx`

### 4.3 Rejected file types

```bash
printf 'x' > /tmp/image.png
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/workspaces/$WS/documents -H "$AUTH" \
  -F "file=@/tmp/image.png;filename=image.png"
```

**Expected:** `HTTP 400` + `{"detail":"Unsupported file type '.png'. Allowed: .pdf, .txt, .docx"}`

Also try `.exe`, `.html`, and a file with **no extension** — all `400`.

### 4.4 File is actually on disk

```bash
ls -la /home/jteckz7/Xvec-chat/uploads/$WS/
```

**Expected:** files named `{document_id}_{original_filename}`

### 4.5 List documents

```bash
curl -s $B/workspaces/$WS/documents -H "$AUTH" | $PY -m json.tool
```

**Expected:** only this workspace's documents. Another user's workspace returns `404`.

### 4.6 Upload to another user's workspace → 404

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/workspaces/$OTHER_WS/documents -H "$AUTH" \
  -F "file=@/tmp/test.txt"
```

**Expected:** `404`

---

## 5. Training

### 5.1 Check status before training

```bash
curl -s $B/workspaces/$WS/documents/$DOC/status -H "$AUTH"
```

**Expected:** `{"doc_id":"...","filename":"...","status":"uploaded","chunk_count":0}`

### 5.2 Start training

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH"
```

**Expected:** `HTTP 202` +
`{"status":"processing","message":"Training started. Use /status to poll."}`

> Training runs in the **background**. The response returns immediately; the server
> keeps working. For a 16-page PDF expect **10–40 s** (embedding model is CPU-bound).

### 5.3 Poll status

```bash
while true; do
  S=$(curl -s $B/workspaces/$WS/documents/$DOC/status -H "$AUTH")
  echo "$(date +%T) $S"
  echo "$S" | grep -q '"ready"\|"failed"' && break
  sleep 2
done
```

**Expected sequence:**
```
... "status":"processing","chunk_count":0
... "status":"ready","chunk_count":14
```

Possible terminal states:
| Status | Meaning |
|---|---|
| `ready` | trained, `chunk_count > 0` |
| `failed` | extraction/chunking/embedding error → see §9 |

### 5.4 Training an already-trained document

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH"
```

**Expected:** `HTTP 200` +
`{"status":"ready","message":"Already trained. Delete and re-upload to retrain."}`

> Retraining requires delete + re-upload, so that the file on disk and the DB stay in sync.

### 5.5 Concurrent training is blocked (409)

Simulate by flipping the status directly:

```bash
cd /home/jteckz7/Xvec-chat/backend
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def m():
    async with get_db() as db:
        await db.execute(\"UPDATE workspace_documents SET status='processing' WHERE id='$DOC'\")
        await db.commit()
asyncio.run(m())
print('status forced to processing')"

curl -s -w "\nHTTP %{http_code}\n" -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH"
```

**Expected:** `HTTP 409` + `{"detail":"Already processing. Wait for it to finish."}`

Restore it:
```bash
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def m():
    async with get_db() as db:
        await db.execute(\"UPDATE workspace_documents SET status='ready' WHERE id='$DOC'\")
        await db.commit()
asyncio.run(m())"
```

### 5.6 Retrying a failed document

```bash
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def m():
    async with get_db() as db:
        await db.execute(\"UPDATE workspace_documents SET status='failed' WHERE id='$DOC'\")
        await db.commit()
asyncio.run(m())"

curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH"
```

**Expected:** `202` — failed documents are retrainable.

### 5.7 Wrong workspace / wrong user → 404

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/workspaces/$WS/documents/nonexistent/train -H "$AUTH"
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH2"
```

**Expected:** `404`, `404`

---

## 6. Chat with a Workspace

> Requires `OPENROUTER_API_KEY` in `.env` (§0.3). Without it → **500**.

### 6.1 Basic question

```bash
curl -s -X POST $B/workspaces/$WS/chat -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is this document about?"}' | $PY -m json.tool
```

**Expected (200)**
```json
{
  "answer": "This document is about TCP port scanning...",
  "sources": [{"filename": "tcp-port-scanner-guide.pdf", "chunk_index": 3}],
  "conversation_history": [
    {"role": "user", "content": "What is this document about?"},
    {"role": "assistant", "content": "This document is about..."}
  ]
}
```

`sources` lists the chunks actually used — one entry per distinct `(filename, chunk_index)`.

### 6.2 Follow-up using conversation history

```bash
HIST=$(curl -s -X POST $B/workspaces/$WS/chat -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarise the key risks in two sentences."}' \
  | $PY -c "import sys,json;print(json.dumps(json.load(sys.stdin)['conversation_history']))")

curl -s -X POST $B/workspaces/$WS/chat -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"And how do I mitigate them?\",\"conversation_history\":$HIST}" | $PY -m json.tool
```

**Expected:** the answer uses earlier turns; returned history has **4** entries.

### 6.3 The workspace system_prompt is used

Ask a workspace created with a distinctive system prompt to prove it is applied:

```bash
WS2=$(curl -s -X POST $B/workspaces -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Pirate WS","system_prompt":"Always answer like a pirate."}' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
```

Train a document into it, then chat — expect pirate-flavoured output.

### 6.4 Tenant isolation (the most important test)

Two workspaces, each with a **different keyword**, owned by **different users**:

```bash
# Workspace A (your user) — content about ZEBRAFISH
WS_A=$WS
printf 'ZEBRAFISH telemetry protocol handles alpha constellation routing and packet inspection. ' > /tmp/alpha.txt
DOC_A=$(curl -s -X POST $B/workspaces/$WS_A/documents -H "$AUTH" -F "file=@/tmp/alpha.txt" \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -o /dev/null -X POST $B/workspaces/$WS_A/documents/$DOC_A/train -H "$AUTH"
sleep 15

# Workspace B (second user) — content about QUOKKA
WS_B=$(curl -s -X POST $B/workspaces -H "$AUTH2" -H "Content-Type: application/json" \
  -d '{"name":"Beta WS"}' | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
printf 'QUOKKA module manages beta subsystem scheduling and resource quotas. ' > /tmp/beta.txt
DOC_B=$(curl -s -X POST $B/workspaces/$WS_B/documents -H "$AUTH2" -F "file=@/tmp/beta.txt" \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -o /dev/null -X POST $B/workspaces/$WS_B/documents/$DOC_B/train -H "$AUTH2"
sleep 15
```

Now ask workspace A about **B's** private keyword:

```bash
curl -s -X POST $B/workspaces/$WS_A/chat -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"message":"What does the QUOKKA module manage?"}' | $PY -m json.tool
```

**Expected:** the answer must **not** contain information about QUOKKA, and
`sources` must be empty or contain **only** workspace A's filenames.

> If workspace A's sources ever include `beta.txt`, **stop** — that is a
> tenant-isolation breach. See §9.6.

### 6.5 Untrained / failed documents are invisible

Ask about a document that was uploaded but never trained:

```bash
DOC_NEW=$(curl -s -X POST $B/workspaces/$WS_A/documents -H "$AUTH" -F "file=@/tmp/alpha.txt" \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST $B/workspaces/$WS_A/chat -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"message":"What about QUOKKA?"}' \
  | $PY -c "import sys,json;d=json.load(sys.stdin);print('sources:',d['sources'])"
```

**Expected:** no sources from the untrained document. Retrieval only uses
chunks whose document status is `ready`.

### 6.6 Chat security

```bash
curl -s -o /dev/null -w "no auth        -> %{http_code}\n" -X POST $B/workspaces/$WS/chat \
  -H "Content-Type: application/json" -d '{"message":"hi"}'
curl -s -o /dev/null -w "other user     -> %{http_code}\n" -X POST $B/workspaces/$WS/chat -H "$AUTH2" \
  -H "Content-Type: application/json" -d '{"message":"hi"}'
curl -s -o /dev/null -w "unknown ws     -> %{http_code}\n" -X POST $B/workspaces/does-not-exist/chat -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"message":"hi"}'
curl -s -o /dev/null -w "empty message  -> %{http_code}\n" -X POST $B/workspaces/$WS/chat -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"message":""}'
```

**Expected:** `401`, `404`, `404`, `422`

---

## 7. Deleting Documents

### 7.1 Delete a trained document

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $B/workspaces/$WS/documents/$DOC_A -H "$AUTH"
```

**Expected:** `204` (no body)

### 7.2 Verify full cleanup

```bash
ls /home/jteckz7/Xvec-chat/uploads/$WS/          # file must be gone

cd /home/jteckz7/Xvec-chat/backend
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def a():
    async with get_db() as db:
        for label, sql, arg in [
            ('workspace_document', 'SELECT COUNT(*) FROM workspace_documents WHERE id=?', '$DOC_A'),
            ('chunks',             'SELECT COUNT(*) FROM chunks WHERE document_id=?', '$DOC_A'),
            ('embeddings',         'SELECT COUNT(*) FROM chunk_embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)', '$DOC_A'),
        ]:
            n = (await (await db.execute(sql, (arg,))).fetchone())[0]
            print(f'{label:20} {n}')
asyncio.run(a())"
```

**Expected:** all `0`, and the upload directory entry removed.

### 7.3 Delete failures

```bash
curl -s -o /dev/null -w "double delete  -> %{http_code}\n" -X DELETE $B/workspaces/$WS/documents/$DOC_A -H "$AUTH"
curl -s -o /dev/null -w "wrong user     -> %{http_code}\n" -X DELETE $B/workspaces/$WS/documents/$DOC_B -H "$AUTH"
curl -s -o /dev/null -w "wrong ws       -> %{http_code}\n" -X DELETE $B/workspaces/$WS_B/documents/$DOC_A -H "$AUTH2"
```

**Expected:** `404`, `404`, `404`

### 7.4 File already deleted from disk → still 204

```bash
rm -f /home/jteckz7/Xvec-chat/uploads/$WS/*        # delete files manually
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $B/workspaces/$WS/documents/$DOC_B -H "$AUTH"
```

**Expected:** `204` — a missing file must not break DB cleanup.

---

## 8. Deleting Workspaces (Cascade)

### 8.1 Delete

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $B/workspaces/$WS_B -H "$AUTH2"
```

**Expected:** `204`

### 8.2 Verify cleanup

```bash
cd /home/jteckz7/Xvec-chat/backend
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def a():
    async with get_db() as db:
        print('workspaces          ', (await (await db.execute(
            'SELECT COUNT(*) FROM workspaces WHERE id=?', ('$WS_B',))).fetchone())[0])
        print('workspace_documents ', (await (await db.execute(
            'SELECT COUNT(*) FROM workspace_documents WHERE workspace_id=?', ('$WS_B',))).fetchone())[0])
        print('embeddings          ', (await (await db.execute(
            '''SELECT COUNT(*) FROM chunk_embeddings WHERE chunk_id IN
               (SELECT c.id FROM chunks c JOIN workspace_documents w ON w.id=c.doc_id
                WHERE w.workspace_id=?)''', ('$WS_B',))).fetchone())[0])
asyncio.run(a())"
```

**Expected:** all `0`

### 8.3 Non-owner cannot delete

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $B/workspaces/$WS -H "$AUTH2"
```

**Expected:** `404`

---

## 9. Troubleshooting

### 9.1 `ModuleNotFoundError: No module named 'backend'`
You used `from backend.app...` imports. The server must be started from `backend/`:
```bash
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
```

### 9.2 `pydantic-core` build failure during pip install
System Python is 3.14, which the pinned versions do not support. Recreate with 3.13:
```bash
cd /home/jteckz7/Xvec-chat
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 9.3 Chat returns 500
Almost always a missing LLM key:
```bash
curl -s $B/api/v1/query/llm/status -H "X-API-Key: dev-key"
```
Set `OPENROUTER_API_KEY` in `.env` and restart. The server log shows the exact reason
(no key / no credits / rate limited / unknown model).

### 9.4 Training stuck at `processing`
Usually the server was restarted mid-training, or a document is huge.
```bash
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def a():
    async with get_db() as db:
        for r in await (await db.execute(
            \"SELECT id,filename,status FROM workspace_documents WHERE status='processing'\"
        )).fetchall():
            print(dict(r))
asyncio.run(a())"
```
To unblock, set the status back:
```bash
../.venv/bin/python -c "
import asyncio
from app.core.database import get_db
async def m():
    async with get_db() as db:
        await db.execute(\"UPDATE workspace_documents SET status='failed'\")
        await db.commit()
asyncio.run(m())
print('reset to failed — now retrainable')"
```

### 9.5 Training says `failed`
| Reason | Fix |
|---|---|
| `no extractable text` | Scanned/image-only PDF — needs OCR, unsupported. Re-upload a text PDF. |
| `Text extraction failed` (PyMuPDF) | File is not a real PDF despite the extension. Re-export it. |
| Empty `.txt` | File has no text content. |
| Corrupt `.docx` | Re-save the document in Word/Google Docs. |
| Out of memory | Very large file. Split it into smaller documents. |

Check the server log (`tail -f /tmp/opencode/uvicorn-ws.log` if started by opencode,
otherwise the terminal running uvicorn) for the exact warning.

### 9.6 Chat returns no sources / wrong sources
```bash
# are the documents trained?
curl -s $B/workspaces/$WS/documents -H "$AUTH" | $PY -c "
import sys,json
for d in json.load(sys.stdin): print(d['status'], d['chunk_count'], d['filename'])"
```
- All `uploaded` → nothing trained yet (§5).
- Sources contain **another workspace's file** → **stop and report**; this is a tenant-isolation breach.
- No sources but documents are `ready` → the question has no keyword/vector overlap with the content. Try a term that literally appears in the document.

### 9.7 `409 Already processing`
Expected when a training run is active. Wait for it to finish, or reset the status
using the snippet in §9.4.

### 9.8 `401` on everything
- Did you export `AUTH` in **this** shell? Variables do not survive new terminals.
- Token older than 7 days → log in again.
- Server restarted with a different `SECRET_KEY` → log in again.

### 9.9 `404 Workspace not found` but you know it exists
- You are using a token for a **different user** (this is by design).
- The workspace was already deleted.
- The shell variable `WS` is empty — re-run §3.1.

### 9.10 `422` on register or chat
- Password < 8 characters.
- Chat `message` empty or > 4000 characters.

### 9.11 Deleted documents still show in legacy `/api/v1/documents/`
**Known issue.** Phase 2 creates an internal `documents` row (needed for the chunk
foreign key); the legacy Phase 1 listing shows it. The row is harmless for Phase 2
chat — workspace chat never reads that endpoint. Fix tracked for a later cleanup task.

### 9.12 `500` with `RuntimeError: OpenRouter ...`
Read the message — it distinguishes: invalid key (401), out of credits (402),
wrong model name (404), rate limit (429).

---

## 10. Full Regression Checklist

Phase 1 must still work. Run after any Phase 2 change.

```bash
# Phase 1 — unchanged
curl -s $B/health
curl -s $B/api/v1/documents/ -H "X-API-Key: dev-key"
curl -s $B/api/v1/query/llm/status -H "X-API-Key: dev-key"
```

Expected: health `ok`, documents list (may contain internal rows, see §9.11), LLM status.

Automated suite:
```bash
cd /home/jteckz7/Xvec-chat/backend
../.venv/bin/python -m pytest app/tests -q
```

Expected: `12 passed, 4 skipped` and **1 known pre-existing failure**:
`test_api_query.py::test_query_returns_answer_with_mock_llm`
(error: `'citations' is already being used as a state key`).
This is a LangGraph version issue in the Phase 1 pipeline, unrelated to Phase 2.
Phase 1's `/api/v1/query/` is therefore still broken — workspace chat
(§6) is the working chat path and is unaffected.

---

## 11. End-to-End Smoke Script

Full happy path in one copy-paste block:

```bash
B=http://localhost:8000
PY=/home/jteckz7/Xvec-chat/.venv/bin/python
EMAIL="e2e-$(date +%s)@test.com"
AUTH="Authorization: Bearer $(curl -s -X POST $B/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"'"$EMAIL"'","password":"password1"}' | $PY -c "import sys,json;print(json.load(sys.stdin)['access_token'])")"

WS=$(curl -s -X POST $B/workspaces -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"E2E","system_prompt":"You are a concise test bot."}' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")

DOC=$(curl -s -X POST $B/workspaces/$WS/documents -H "$AUTH" \
  -F "file=@/home/jteckz7/Xvec-chat/tcp-port-scanner-guide.pdf" \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "workspace=$WS doc=$DOC"
curl -s -X POST $B/workspaces/$WS/documents/$DOC/train -H "$AUTH"; echo

for i in $(seq 1 40); do
  S=$(curl -s $B/workspaces/$WS/documents/$DOC/status -H "$AUTH")
  echo "$S"
  echo "$S" | grep -q '"ready"\|"failed"' && break
  sleep 2
done

curl -s -X POST $B/workspaces/$WS/chat -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"message":"What is this guide about?"}' | $PY -m json.tool

curl -s -o /dev/null -w "delete doc -> %{http_code}\n" -X DELETE $B/workspaces/$WS/documents/$DOC -H "$AUTH"
curl -s -o /dev/null -w "delete ws  -> %{http_code}\n" -X DELETE $B/workspaces/$WS -H "$AUTH"
```

**All of these must succeed:** register → workspace → upload → train → ready → chat → delete → 204 → 204.

---

## 12. Feature Reference

### Endpoints added in Phase 2

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | 201; 400 if email exists |
| POST | `/auth/login` | — | 200; 401 if bad credentials |
| POST | `/workspaces` | JWT | 201; owner from token |
| GET | `/workspaces` | JWT | own workspaces only |
| GET | `/workspaces/{id}` | JWT | 404 if not owner |
| PUT | `/workspaces/{id}` | JWT | partial update |
| DELETE | `/workspaces/{id}` | JWT | 204; cascades docs + vectors |
| POST | `/workspaces/{id}/documents` | JWT | multipart; pdf/txt/docx |
| GET | `/workspaces/{id}/documents` | JWT | own workspace only |
| DELETE | `/workspaces/{id}/documents/{doc_id}` | JWT | 204; file + chunks + vectors |
| POST | `/workspaces/{id}/documents/{doc_id}/train` | JWT | 202 / 200 / 409 |
| GET | `/workspaces/{id}/documents/{doc_id}/status` | JWT | poll training |
| POST | `/workspaces/{id}/chat` | JWT | workspace-scoped RAG answer |

### Document status lifecycle

```
uploaded ──train──► processing ──► ready
                        │
                        └──────► failed ──train──► processing ...
```

### Configuration

| Setting | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `change-this-in-production` | JWT signing — **change in production** |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | Token lifetime |
| `UPLOAD_DIR` | `./uploads` | Phase 2 upload root |
| `upload_dir` | `./data/uploads` | Legacy Phase 1 uploads (duplication, cleanup pending) |

### Data model

```
users ──1:N──► workspaces ──1:N──► workspace_documents
                                          │
                                          └──► chunks (workspace_id, doc_id)
                                                     │
                                                     └──► chunk_embeddings (sqlite-vec)
```

Retrieval filters on `chunks.workspace_id` **and** requires the source document
status to be `ready`, so a tenant can only ever see their own trained content.
