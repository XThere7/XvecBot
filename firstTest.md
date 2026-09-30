# XvecBot — Phase 2 & 3 Integration Test Record

**Tester:** QA Agent
**Date:** 2026-09-28
**Server:** http://127.0.0.1:8000
**Test Identity:** email `qa.tester@xvecbot.com`, password `QaTest1234!`

Results are appended immediately after each test completes.

---

## Phase 2 — Authentication

### T2.1 Health check
- **Request:** `GET /health`
- **Expected:** 200, status ok
- **Response:** `{"status":"ok","app":"production-rag","version":"1.0.0","timestamp":"2026-09-28T21:52:47.856519+00:00","uptime_seconds":706.6}` — HTTP 200
- **Result:** PASS

### T2.2 Register
- **Request:** `POST /auth/register` body `{"email":"qa.tester@xvecbot.com","password":"QaTest1234!"}`
- **Expected:** 201, access_token + user_id
- **Response:** `{"access_token":"eyJhbGciOiJIUzI1NiIs...exp:1791237195...","token_type":"bearer","user_id":"5f9ad10a-7865-4281-9ac4-2abf3eafad4e"}` — HTTP 201
- **Result:** PASS

### T2.3 Register duplicate email
- **Request:** `POST /auth/register` same body
- **Expected:** 400 "Email already registered"
- **Response:** `{"detail":"Email already registered"}` — HTTP 400
- **Result:** PASS

### T2.4 Login success
- **Request:** `POST /auth/login` body `{"email":"qa.tester@xvecbot.com","password":"QaTest1234!"}`
- **Expected:** 200, access_token
- **Response:** `{"access_token":"eyJhbGciOiJIUzI1NiIs...","token_type":"bearer","user_id":"5f9ad10a-..."}` — HTTP 200
- **Result:** PASS

### T2.5 Login wrong password
- **Request:** `POST /auth/login` body `{"email":"qa.tester@xvecbot.com","password":"wrongpass1"}`
- **Expected:** 401 "Invalid credentials"
- **Response:** `{"detail":"Invalid credentials"}` — HTTP 401
- **Result:** PASS

---

## Phase 2 — Workspaces

### T2.6 Create workspace
- **Request:** `POST /workspaces` body `{"name":"QA Workspace","description":"for integration tests","system_prompt":"You are QA assistant."}`
- **Expected:** 201, full workspace object
- **Response:** `{"id":"8b4c48d9-4bb7-4299-b3f1-2f3ac1cf8393","name":"QA Workspace","description":"for integration tests","system_prompt":"You are QA assistant.","owner_id":"5f9ad10a-...","created_at":"2026-09-28T21:54:19.277660+00:00"}` — HTTP 201
- **Result:** PASS

### T2.7 List workspaces
- **Request:** `GET /workspaces`
- **Expected:** 200, array with the workspace
- **Response:** `[{"id":"8b4c48d9-...","name":"QA Workspace",...}]` — HTTP 200
- **Result:** PASS

### T2.8 Get workspace
- **Request:** `GET /workspaces/8b4c48d9-4bb7-4299-b3f1-2f3ac1cf8393`
- **Expected:** 200, single workspace
- **Response:** full workspace object — HTTP 200
- **Result:** PASS

### T2.9 Update workspace (partial)
- **Request:** `PUT /workspaces/8b4c48d9-...` body `{"description":"updated desc"}`
- **Expected:** 200, description changed, name/system_prompt unchanged
- **Response:** `{"id":"8b4c48d9-...","name":"QA Workspace","description":"updated desc","system_prompt":"You are QA assistant.",...}` — HTTP 200
- **Result:** PASS

---

## Phase 2 — Documents

### T2.10 Upload PDF
- **Request:** `POST /workspaces/8b4c48d9-.../documents` multipart `file=@tcp-port-scanner-guide.pdf`
- **Expected:** 201, status "uploaded", chunk_count 0
- **Response:** `{"id":"664b59bf-2ee4-4251-8134-df0966ee597b","workspace_id":"8b4c48d9-...","filename":"tcp-port-scanner-guide.pdf","file_path":".../data/uploads/8b4c48d9-.../664b59bf-..._tcp-port-scanner-guide.pdf","file_type":"pdf","size_bytes":263868,"status":"uploaded","chunk_count":0,"created_at":"2026-09-28T21:55:20..."}` — HTTP 201
- **Result:** PASS

### T2.11 Upload rejected file type
- **Request:** `POST /workspaces/8b4c48d9-.../documents` multipart `file=bad.png`
- **Expected:** 400 "Unsupported file type"
- **Response:** `{"detail":"Unsupported file type '.png'. Allowed: .pdf, .txt, .docx"}` — HTTP 400
- **Result:** PASS

### T2.12 Train document
- **Request:** `POST /workspaces/8b4c48d9-.../documents/664b59bf-.../train`
- **Expected:** 202 "Training started"
- **Response:** `{"status":"processing","message":"Training started. Use /status to poll."}` — HTTP 202
- **Result:** PASS

### T2.13 Poll training status
- **Request:** `GET /workspaces/8b4c48d9-.../documents/664b59bf-.../status` (polled)
- **Expected:** terminal status "ready" with chunk_count > 0
- **Response:** `{"doc_id":"664b59bf-...","filename":"tcp-port-scanner-guide.pdf","status":"ready","chunk_count":14}`
- **Result:** PASS

### T2.14 Workspace chat
- **Request:** `POST /workspaces/8b4c48d9-.../chat` body `{"message":"What is this document about?"}`
- **Expected:** 200, grounded answer, sources, history
- **Response:** HTTP 200 — answer: *"This document is a tutorial about building a TCP port scanner in C++17. It covers networking fundamentals (IPv4 addresses, ports, TCP three-way handshake)..."*; sources: 5 entries all `tcp-port-scanner-guide.pdf`; history len 2
- **Result:** PASS

### T2.15 Delete document
- **Request:** `DELETE /workspaces/8b4c48d9-.../documents/664b59bf-...`
- **Expected:** 204, then list empty
- **Response:** HTTP 204; subsequent `GET .../documents` → `[]` HTTP 200
- **Result:** PASS

---

## Phase 3 — Agents

### T3.1 Create Agent A
- **Request:** `POST /workspaces/8b4c48d9-.../agents` body `{"name":"Support Agent","system_prompt":"You are a professional support agent. Be concise.","temperature":0.3}`
- **Expected:** 201, defaults applied
- **Response:** HTTP 201 — `model: meta-llama/llama-3.3-70b-instruct:free | temp: 0.3 | lang: English | active: 1`, id `21e29af1-d17a-477f-a59f-d5ce50e4c5db`
- **Result:** PASS

### T3.2 Create Agent B
- **Request:** `POST /workspaces/8b4c48d9-.../agents` body `{"name":"Storyteller Agent","system_prompt":"You are a creative storyteller.","temperature":0.9}`
- **Expected:** 201
- **Response:** HTTP 201 — temp 0.9, id `e44f9b63-7b15-4ce8-a385-60acf4b12ef0`
- **Result:** PASS

### T3.3 List agents
- **Request:** `GET /workspaces/8b4c48d9-.../agents`
- **Expected:** 200, both agents
- **Response:** HTTP 200 — count 2, names `['Storyteller Agent', 'Support Agent']`
- **Result:** PASS

### T3.4 Get single agent
- **Request:** `GET /workspaces/8b4c48d9-.../agents/21e29af1-...`
- **Expected:** 200
- **Response:** HTTP 200
- **Result:** PASS

### T3.5 Update agent (partial)
- **Request:** `PUT /workspaces/8b4c48d9-.../agents/21e29af1-...` body `{"temperature":0.2}`
- **Expected:** 200, only temperature changed
- **Response:** HTTP 200 — temp 0.2, name "Support Agent" (unchanged)
- **Result:** PASS

### T3.6 Create agent — validation errors
- **Request A:** `POST .../agents` body `{"name":"","system_prompt":"valid prompt here"}`
- **Response A:** HTTP 422 — `{"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character",...}]}`
- **Request B:** `POST .../agents` body `{"name":"X","system_prompt":"short"}`
- **Response B:** HTTP 422 — `{"detail":"System prompt must be at least 10 characters (got 5)."}`
- **Result:** PASS (both correctly rejected)

### T3.7 Chat Agent A (new conversation)
- **Request:** `POST /workspaces/8b4c48d9-.../agents/21e29af1-.../chat` body `{"message":"Tell me what you know."}`
- **Expected:** 200, grounded answer, sources, model_used
- **Response:** HTTP 200 — `model_used: openrouter/free` (primary model 404 → fallback), answer: *"Based on the provided document, here's what I know: **Project Overview** - This is a C++17 TCP port scanner implementation..."*, 5 sources, conv_id `76184269-ef89-40bb-9081-833b7fa5ebd5`
- **Result:** PASS

### T3.8 Chat Agent B (different personality)
- **Request:** `POST /workspaces/8b4c48d9-.../agents/e44f9b63-.../chat` body `{"message":"Tell me what you know."}`
- **Expected:** 200, answer reflects Agent B's "creative storyteller" personality
- **Response:** HTTP 200 — answer: *"**What I know, drawn entirely from the provided document:** ### Project Overview - **Title:** *From Scratch: Building a TCP Port Scanner in C++*..."* (more elaborate/storytelling tone vs Agent A's concise tone)
- **Result:** PASS

### T3.9 Continue Agent A conversation — **BUG FOUND + FIXED**
- **Request:** `POST /workspaces/8b4c48d9-.../agents/21e29af1-.../chat` body `{"message":"And what else?","conversation_id":"76184269-..."}`
- **Initial result:** **FAIL** — HTTP 500 `{"detail":"Chat failed. Check server logs."}`, empty answer, new conversation created
- **Diagnosis:** Server log showed `OpenRouter returned an unexpected response shape ... 'finish_reason': 'length'`. Root cause: `.env` set `LLM_MAX_TOKENS=512`; with conversation history + retrieved context the model hit the token limit and returned `content: null`. The generator's `data["choices"][0]["message"]["content"].strip()` then raised `AttributeError` on `None`, which was misreported as "unexpected response shape".
- **Fixes applied:**
  1. `llm/openrouter_generator.py` — extract content with `.get("content")`; raise a clear `ModelCallError` naming `finish_reason` when content is `None` (instead of a misleading "unexpected response shape").
  2. `.env` — `LLM_MAX_TOKENS=512` → `4096` (the actual truncation cause).
  3. `core/config.py` — default `llm_max_tokens` raised `1024` → `4096` to match.
- **Re-test after fix:** HTTP 200 — `same conv: True`, answer: *"The document also covers: * Legal and ethical boundaries of port scanning. * Concrete extensions to build next..."* (aware of previous turn), 5 sources
- **Result:** PASS (after fix)

### T3.10 List conversations (auto-title)
- **Request:** `GET /workspaces/8b4c48d9-.../agents/21e29af1-.../conversations`
- **Expected:** 200, thread with auto-generated title
- **Response:** HTTP 200 — count 1, title `'Tell me what you know.'` (auto-generated from first message)
- **Result:** PASS

### T3.11 Pre-create empty conversation
- **Request:** `POST /workspaces/8b4c48d9-.../agents/21e29af1-.../conversations/new`
- **Expected:** 201, empty conversation
- **Response:** HTTP 201 — `{"id":"e442e6f8-...","title":"New Conversation","agent_id":"21e29af1-...","created_at":"...","updated_at":"..."}`
- **Result:** PASS

### T3.12 Get single conversation with messages
- **Request:** `GET /workspaces/8b4c48d9-.../agents/21e29af1-.../conversations/e442e6f8-...`
- **Expected:** 200, `{"conversation": {...}, "messages": [...]}`
- **Response:** HTTP 200 — `{"conversation":{"id":"e442e6f8-...","title":"New Conversation",...},"messages":[]}`
- **Result:** PASS

### T3.13 Delete conversation
- **Request:** `DELETE /workspaces/8b4c48d9-.../agents/21e29af1-.../conversations/e442e6f8-...`
- **Expected:** 204, then GET → 404
- **Response:** HTTP 204; subsequent GET → HTTP 404
- **Result:** PASS

### T3.14 Delete agent (cascades)
- **Request:** `DELETE /workspaces/8b4c48d9-.../agents/e44f9b63-...` (Agent B)
- **Expected:** 204, agent gone, list shows 1
- **Response:** HTTP 204; `GET .../agents/e44f9b63-...` → 404; list → count 1 `['Support Agent']`
- **Result:** PASS

### T3.15 Multi-tenant isolation (second user `qa.attacker@xvecbot.com`)
- **Requests (all as attacker against victim workspace `8b4c48d9-...`):**
  - `GET /workspaces/8b4c48d9-.../agents` → **403**
  - `GET /workspaces/8b4c48d9-.../agents/21e29af1-...` → **403**
  - `POST /workspaces/8b4c48d9-.../agents/21e29af1-.../chat` → **403**
  - `GET /workspaces/8b4c48d9-.../agents/21e29af1-.../conversations` → **403**
  - `GET /workspaces/8b4c48d9-.../agents` (no auth) → **401**
- **Result:** PASS (all correctly forbidden)

### T3.16 Config validation — soft fallbacks
- **Unsupported model:** `POST .../agents` body `{"name":"Fallback Model","system_prompt":"You are a test agent.","model":"not-a-real-model"}` → HTTP 201, `model: meta-llama/llama-3.3-70b-instruct:free` (default)
- **Unsupported language:** body `{"name":"Fallback Lang","system_prompt":"You are a test agent.","language":"Klingon"}` → HTTP 201, `language: English` (default)
- **Out-of-range temperature:** body `{"name":"Clamp Temp","system_prompt":"You are a test agent.","temperature":9.9}` → HTTP 201, `temperature: 1.0` (clamped)
- **Result:** PASS

### T2.16 Train already-trained document
- **Request:** `POST /workspaces/8b4c48d9-.../documents/813ebdf0-.../train` (already ready)
- **Expected:** 200 "Already trained"
- **Response:** `{"status":"ready","message":"Already trained. Delete and re-upload to retrain."}` — HTTP 200
- **Result:** PASS

### T2.17 Chat in workspace with no trained documents
- **Request:** `POST /workspaces/{empty-ws}/chat` body `{"message":"What do you know?"}`
- **Expected:** 200, graceful "no context" answer, empty sources
- **Response:** HTTP 200 — answer: *"I could not find relevant information in this workspace's documents to answer your question."*, sources: `[]`
- **Result:** PASS

### T2.18 Delete workspace (cascade)
- **Request:** `DELETE /workspaces/8b4c48d9-...`
- **Expected:** 204, workspace + agents gone
- **Response:** HTTP 204; `GET /workspaces/8b4c48d9-...` → 404; `GET .../agents` → 404; list → count 1 `['Empty WS']`
- **Result:** PASS

---

## Bug Fix Summary

| # | Bug | Root cause | Fix |
|---|---|---|---|
| 1 | Agent chat follow-up returned HTTP 500 with empty answer | `.env` set `LLM_MAX_TOKENS=512`; with history the model hit the limit and returned `content: null`, which crashed `.strip()` and was misreported as "unexpected response shape" | `.env` → `LLM_MAX_TOKENS=4096`; `core/config.py` default → 4096; `openrouter_generator.py` now raises a clear `ModelCallError` naming `finish_reason` when content is `None` |

---

## Final Tally

- **Phase 2 tests:** 18 passed (T2.1–T2.18)
- **Phase 3 tests:** 16 passed (T3.1–T3.16), including 1 bug found and fixed (T3.9)
- **Total:** 34/34 passed after fix
- **Multi-tenant isolation:** verified (403 for non-owner, 401 unauthenticated)
- **Config validation:** hard violations → 422; soft violations → default fallback

### T2.19 Upload TXT
- **Request:** `POST /workspaces/{ws}/documents` multipart `file=notes.txt`
- **Response:** HTTP 201 — `file_type: txt`, `status: uploaded`
- **Result:** PASS

### T2.20 Upload DOCX
- **Request:** `POST /workspaces/{ws}/documents` multipart `file=spec.docx`
- **Response:** HTTP 201 — `file_type: docx`, `status: uploaded`
- **Result:** PASS

---

## Final Tally (updated)

- **Phase 2 tests:** 20 passed (T2.1–T2.20)
- **Phase 3 tests:** 16 passed (T3.1–T3.16), including 1 bug found and fixed (T3.9)
- **Total:** 36/36 passed after fix
