# XvecBot Dashboard — Frontend Specification

**Document version:** 1.0 · **Date:** 2026-10-01 · **Status:** Ready for design & build

This is the complete, authoritative specification for the XvecBot platform dashboard. It was written
against the **live backend** and every field name, status code, enum value and default in this
document was verified against a running server. If this document and the backend ever disagree,
this document is correct as of the version date.

**Audience:** a UI/UX designer and a frontend developer who have never seen the codebase and must not
need to ask the backend team a single question.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [User Flows](#2-user-flows-end-to-end-journeys)
3. [Information Architecture](#3-information-architecture-site-map)
4. [Page-by-Page Specification](#4-page-by-page-specification)
5. [Component Library](#5-component-library)
6. [API Integration Guide](#6-api-integration-guide)
7. [Design System](#7-design-system)
8. [Responsive Behaviour](#8-responsive-behaviour)
9. [Key UX Decisions (Mandatory Rules)](#9-key-ux-decisions-explicit-rules)
10. [Frontend Tech Stack](#10-frontend-tech-stack-recommendation)
11. [Folder Structure](#11-folder-structure)
12. [Environment Variables](#12-environment-variables)
13. [Handoff Notes for the Designer](#13-handoff-notes-for-the-designer)
14. [Handoff Notes for the Developer](#14-handoff-notes-for-the-developer)
15. [Appendix A — Verified API Reference](#15-appendix-a--verified-api-reference)
16. [Appendix B — Corrections to the Original API Brief](#16-appendix-b--corrections-to-the-original-api-brief)

---

## 1. Product Overview

XvecBot is a B2B SaaS platform, built and operated in Tanzania, that lets a business owner turn their
own documents — product catalogues, price lists, handbooks, SOPs, terms — into an AI agent they can
embed on their website as a chat widget, with no AI expertise required. The platform user is a
non-technical business owner or marketing manager. Their entire journey has three parts: **manage
knowledge** (upload and train documents in a workspace), **build agents** (configure a persona,
model, tone and welcome message over that knowledge), and **deploy widgets** (generate an embed
token, paste one script tag into their site, and monitor usage). Everything else in this document
exists to serve those three jobs.

---

## 2. User Flows (End-to-End Journeys)

Nine flows. Each is written start state → steps → end state, at the level of "what screen am I on,
what do I click, what does the API do".

### Flow 1 — First-time registration and onboarding

**Start state:** Signed out, no account, lands on `/login` (or redirected there from any protected
route).

1. **Landing on `/register`.** Split layout: left = form, right = brand panel with a 3-step
   "how it works" illustration (Upload → Train → Embed). Email and password inputs, a
   "Create account" primary button, and a link to `/login`. Nothing is pre-filled.
2. **Enter email + password.** Client-side validation fires on blur and on submit:
   email must match a basic email pattern; password ≥ 8 characters. Inline error text renders under
   the offending field in `danger` colour. Do **not** block typing while validating — validate on
   submit first, then on blur.
3. **Submit.** Button enters `loading` (spinner, disabled). `POST /auth/register`.
   - `201` → store JWT, route to `/dashboard`.
   - `400` (`{"detail":"Email already registered"}`) → show the server message directly under the
     email field, and add a "Log in instead?" link.
   - `422` → map the validation array to fields (see [§6.1](#61-error-shape-normalisation)).
   - `409`/`500` → toast: "Something went wrong. Please try again."
4. **Onboarding empty state at `/dashboard`.** This is the most important first-run screen. It is a
   three-card checklist, not a blank dashboard:
   - Card 1 — "Create a workspace" (CTA → `/workspaces/new`)
   - Card 2 — "Upload a document" (disabled + lock icon until a workspace exists)
   - Card 3 — "Create your first agent" (disabled until ≥1 document is `ready`)
   Each completed card collapses to a single checked row. Progress is derived from real API data,
   never stored client-side.

**End state:** User is on `/dashboard` with a zero-data account, seeing the 3-step checklist.

### Flow 2 — Creating a workspace

**Start state:** On `/dashboard` (no workspaces) or `/workspaces`.

1. Click **New workspace** → route to `/workspaces/new`.
2. Form: **Name** (required, 1–100 chars), **Description** (optional, plain text, shown in the
   workspace switcher), **Default system prompt** (optional textarea, prefilled with
   `You are a helpful assistant.` — the API's own default). A hint under the textarea:
   *"This is the baseline instruction for workspace-level chat. Each agent can override it."*
3. Submit → `POST /workspaces` → `201`. Redirect to `/workspaces/[id]` (documents tab).
   Toast: "Workspace created."
4. Validation: name required, ≤ 100 chars. Everything else optional.

**End state:** Empty workspace at `/workspaces/[id]`, Documents tab, empty state prompting an upload.

### Flow 3 — Uploading and training a document (including the polling wait state)

**Start state:** `/workspaces/[id]` → Documents tab, empty or with existing documents.

1. **Upload zone.** A dashed-border dropzone at the top of the list. Drag-and-drop or click to open
   a file picker (`accept=".pdf,.txt,.docx"`). Multiple files may be dropped; they upload
   **sequentially**, one at a time.
2. **Client-side pre-checks before any network call:**
   - extension must be `.pdf`, `.txt` or `.docx` → otherwise block and show
     "Unsupported file type. Allowed: .pdf, .txt, .docx"
   - the backend enforces **no server-side size cap** on this route, but the recommended client-side
     cap is **50 MB** (matching the platform's other upload route). Warn above 50 MB rather than
     silently accepting.
3. **Upload.** `POST /workspaces/{ws}/documents` as `multipart/form-data`, field name **`file`**.
   The row appears in an **optimistic pending** state immediately (grey badge, `Upload…`), with a
   cancel affordance that only removes the row locally (the request cannot be aborted server-side).
   - `201` → replace the optimistic row with the real document, `status: "uploaded"`.
   - `400` → mark that row `failed` with the server's message.
   - `404` → toast "Workspace not found." and stop the queue.
4. **Training.** The UI must decide whether to auto-train. Recommended default: **auto-train
   immediately after a successful upload**, no extra click — the user asked to "add knowledge". A
   manual **Train** button remains on every document so a `failed` document can be retried.
   `POST /workspaces/{ws}/documents/{doc_id}/train`.
   - `202` → `{status: "processing"}`. Start polling.
   - `200` → `{status: "ready"}`. Already trained; do not poll.
   - `409` → another training run is already in flight. Do not poll from this component; the status
     poll already running will pick it up. Show `processing` and suppress duplicate toasts.
5. **Polling wait state.** See [§6.4](#64-document-training-poll-loop). `GET .../status` every 3
   seconds. The row shows a yellow animated `processing` badge and a thin indeterminate progress bar
   that fills left-to-right in a loop (do not fake a percentage — the API never returns one).
6. **Terminal states:**
   - `ready` → green badge, show `chunk_count` ("412 chunks"). Stop polling. Toast: "Training
     complete."
   - `failed` → red badge, stop polling. Toast: "Training failed. Check the file and retry."
7. **Bulk.** While any document is `processing`, the page header shows "N documents training…". When
   the last one finishes, refresh the document list and the workspace-level agent gating, because a
   newly-ready document may unblock agent creation.

**End state:** All documents `ready`, `chunk_count` visible per row, agent creation now unblocked.

### Flow 4 — Creating and configuring an agent

**Start state:** `/workspaces/[id]` → Agents tab.

1. **Prerequisite gate.** If the workspace has **zero documents in `ready` state**, the **New agent**
   button is disabled with a tooltip and an inline prompt: *"Train at least one document before
   creating an agent — an agent with no knowledge base cannot answer."* A `failed`/`processing`
   document does not count. This is a hard rule, not a suggestion ([§9.7](#97-disabled-states-for-unmet-prerequisites)).
2. Click **New agent** → `/workspaces/[id]/agents/new`.
3. Form fields, in this order:
   - **Name** — required, 1–100. Shown in the widget header, so tell the user it is customer-facing.
   - **Description** — optional. Shown in the dashboard agent list.
   - **System prompt** — required, ≥ 1 char. A large textarea with a placeholder that teaches:
     *"You are Acme Store's support assistant. Answer only from the knowledge base. If the answer is
     not in the documents, say so plainly."*
   - **Welcome message** — optional, ≤ 500 chars, with a live character counter. Help text:
     *"The first thing visitors see when they open the chat. Leave empty for the default greeting.
     This is the only message shown before the visitor sends anything."*
   - **Model** — dropdown. **There is no API that lists models**, so this list is hardcoded from
     [§6.7](#67-model-dropdown-reference-data) and must be kept in sync with the backend.
   - **Temperature** — slider, 0.0–1.0, step 0.1, default 0.7. Show a live value + a plain-language
     caption ("Precise ←→ Creative").
   - **Language** — dropdown from a hardcoded list of 5 (also no API). See [§6.7](#67-model-dropdown-reference-data).
4. Submit → `POST /workspaces/{ws}/agents` → `201`. Redirect to
   `/workspaces/[id]/agents/[agent_id]` (Overview tab). Toast: "Agent created."
5. **Validation:** name and system_prompt required; welcome_message ≤ 500; temperature clamped to
   0–1 (the backend soft-clamps rather than rejecting, so the UI must clamp too or the two
   will disagree).

**End state:** Agent detail page, `is_active: 1`, ready to test.

### Flow 5 — Testing the agent via the in-dashboard chat preview

**Start state:** `/workspaces/[id]/agents/[agent_id]` → **Test** tab.

1. A **docked panel** (not the floating widget — see [§9.8](#98-dashboard-preview-vs-public-widget)).
   Layout: message list on top, composer pinned to the bottom, sources rendered as citation chips
   beneath each assistant answer. A "New conversation" ghost button sits in the panel header.
2. The user types and submits → `POST /workspaces/{ws}/agents/{agent_id}/chat` with
   `{ message, conversation_id }`. `conversation_id` starts **`null`**.
3. Show an animated typing indicator; disable the send button while in flight.
4. On `200`: replace the indicator, append the answer, render `sources[]` as chips
   (`filename` + optional `chunk_index`), and **store the returned `conversation_id`** for the next
   turn. Also show `model_used` as a subtle caption under the answer (the dashboard is the only
   place this is ever visible).
5. `sources` may be `[]` when retrieval finds nothing. Never render an empty container — show a
   "No sources found" caption so the user understands the answer was not grounded.
6. A **grounding warning** should be visually distinct (amber left-border on the bubble) whenever
   `sources.length === 0`. This is the single most valuable signal in the preview and directly
   predicts widget quality.

**End state:** A conversation that proves the agent answers from the merchant's own documents.

### Flow 6 — Generating an embed token and getting the snippet

**Start state:** `/workspaces/[id]/agents/[agent_id]` → **Embed** tab (or Tokens sub-tab).

1. **Token list.** Table with columns: Label, Status (active toggle), Allowed origins, Requests,
   Last used, Created, Row actions (Copy snippet, Edit, Revoke/Reactivate, Delete). Token values are
   **masked** (`a3f7c91b…`) — the full value is never returned by list or get.
2. **Create token.** Button opens a modal:
   - **Label** (required, 1–100) — e.g. "acmestore.co.tz"
   - **Allowed origins** (optional) — a **chip/tag input**. Empty = allow any origin. Each chip is a
     bare hostname (`mystore.co.tz`) — no protocol, no path. A helper line is mandatory:
     *"Leave empty to allow the widget on any domain. Add hostnames to lock it down — matching is
     exact, so `mystore.co.tz` and `www.mystore.co.tz` are different entries."*
   - Optional advanced row: **Position** (`right`/`left`) and **Colour** (hex, default `#6366f1`) —
     these are rendered into the snippet as `data-position` / `data-color`.
3. Submit → `POST .../tokens` → `201`. **This is the only moment the full token exists in the
   browser.** Immediately open the "Save your token" modal — see [§9.3](#93-the-full-token-is-shown-once--mandatory-ui-treatment).
4. **Snippet display.** A dark code block with syntax-highlighted HTML, a **Copy** button
   (with a copied confirmation), and a link "Open the full token" that calls
   `GET .../tokens/{id}/snippet`. The snippet looks like:

   ```html
   <!-- XvecBot chat widget -->
   <script src="https://api.xvecbot.tz/widget.min.js"
           data-agent="ebbe02514ec6eab6ee0586769b208595851e98a7116dec209ce4a2418a388556"
           data-position="right"
           data-color="#6366f1"
           async></script>
   ```

   `data-agent` **always** carries the full 64-character token. Two more tabs of context should sit
   above the code block: "Paste before `</body>`" and "Works on any website — no build step."
5. **Success guidance.** After copying, show a 3-step checklist: (1) snippet copied,
   (2) pasted before `</body>`, (3) widget visible on the live site. Let the user tick these off
   locally. A "Test it" button opens the paste page in a new tab.

**End state:** Merchant has a working widget on their site.

### Flow 7 — Viewing conversation history

**Start state:** `/workspaces/[id]/agents/[agent_id]` → **Conversations** tab.

1. **List view.** Rows ordered `updated_at` descending (most recent first — see
   [§9.9](#99-conversation-history-ordering-and-titles)). Columns: Title, Message count (if
   cheaply available), Updated (relative time, absolute on hover), Actions (Open, Delete).
2. **Empty state.** "No conversations yet." + button "Start a conversation" that deep-links to the
   Test tab.
3. **Thread view** at `.../conversations/[id]`. `GET .../conversations/{id}` returns
   `{ conversation, messages }` — one round trip, render both. Messages are user/assistant bubbles
   with timestamps; assistant messages render their `sources` chips when present.
4. Read-only. A banner states *"This is a preview of a stored conversation. To continue chatting,
   open the Test tab."* — because the dashboard chat endpoint is the only way to append.
5. Delete a conversation → confirmation dialog (see [§9.4](#94-mandatory-confirmation-dialogs)).

**End state:** The merchant can audit what their visitors actually asked.

### Flow 8 — Revoking / managing embed tokens

**Start state:** Tokens list on any agent.

1. **Revoke (soft).** Toggle `is_active` off in the row, or open the row menu → **Revoke**.
   `PUT .../tokens/{id}` with `{ "is_active": false }`. Immediate optimistic flip; revert on error.
   Toast: "Token revoked. The widget will stop responding immediately." Explain the consequence in
   the confirmation: this is the "kill switch" for a compromised or misconfigured widget.
2. **Reactivate.** Same endpoint with `{ "is_active": true }`.
3. **Edit.** Label and allowed origins in a modal → `PUT` with only the changed fields.
   - **Constraint:** the backend ignores `null` values on update, so **you cannot clear a field back
     to `null`** this way. To clear allowed origins, send `[]` (empty array) which the backend stores
     as `null` = allow all. To reset a welcome message, send `" "` (a space) — the public API treats a
     blank value as "use the default". Document this in the UI as helper text.
4. **Copy snippet again.** Calls `GET .../snippet`, which is the only endpoint that returns the full
   token after creation. Copying works even for a revoked token.
5. **Usage readouts.** `request_count` and `last_used_at` come straight from the API. Render
   `request_count` as a number and `last_used_at` as relative time ("3 minutes ago") or "Never".
   Note for the designer's copy: the counter increments on *every* widget call including the
   agent-info fetch, so it is "widget requests", not strictly "messages sent".

**End state:** Full control over which embed tokens can talk to the platform.

### Flow 9 — Deleting an agent or workspace

**Start state:** Agent detail, workspace settings, or the Tokens/Conversations list.

1. **Delete agent** → confirmation dialog, type-to-confirm not required but the copy must state the
   consequences: the agent, **all of its conversations**, and **all of its embed tokens are
   permanently deleted**, and any live widget using those tokens stops working immediately.
2. `DELETE .../agents/{agent_id}` → `204`. Redirect to the Agents list. Toast: "Agent deleted."
3. **Delete workspace** → same pattern with a heavier warning: documents, chunks, embeddings, all
   agents, all conversations and all tokens are destroyed; the operation is irreversible and there
   is no undo. Recommend exporting/keeping the snippet elsewhere first.
4. `DELETE /workspaces/{id}` → `204`. Redirect to `/workspaces`. Toast: "Workspace deleted."
5. Never optimistically delete a workspace — cascade size makes failure expensive to interpret.

**End state:** Resource removed; user returned to the parent list.

---

## 3. Information Architecture (Site Map)

```
/                                   → redirect to /dashboard (or /login if signed out)
/login                              → Sign in
/register                           → Create account
/onboarding                         → 3-step checklist (redirects to /dashboard; kept as a route for deep links)

/dashboard                          → Home overview
  ├─ onboarding checklist (inline, not a route)
  └─ recent activity (inline)

/workspaces                         → Workspace switcher + list
  └─ /workspaces/new                 → Create workspace form

/workspaces/[wsId]                   → Workspace detail (tabbed)
  ├─ ?tab=documents   (default)      → Document list, upload zone, training status
  │   └─ (document detail is a drawer, not a route)
  ├─ ?tab=agents                     → Agent cards grid
  │   ├─ /workspaces/[wsId]/agents/new          → Create agent form
  │   └─ /workspaces/[wsId]/agents/[agentId]    → Agent detail (tabbed)
  │       ├─ ?tab=overview   (default)          → Config summary + inline edit
  │       ├─ ?tab=test                        → Chat preview (docked panel)
  │       ├─ ?tab=conversations                → Conversation list
  │       │   └─ /workspaces/[wsId]/agents/[agentId]/conversations/[convId]  → Thread view
  │       └─ ?tab=embed                        → Embed tokens + snippet
  └─ ?tab=settings                   → Workspace settings, rename, delete

/account                            → Profile, password, logout
/account/security                   → Session & API information
```

**Global (rendered outside the router tree):**

- Sidebar navigation (persistent, desktop)
- Top bar (breadcrumb + workspace switcher + account menu)
- Toast viewport
- Global command palette (optional, `⌘K`)

**Route-to-API map (every route and what it must fetch):**

| Route | Fetches on load |
|---|---|
| `/login` | — |
| `/register` | — |
| `/dashboard` | `GET /workspaces`, then per workspace: agents + documents (or a summary endpoint if added later) |
| `/workspaces` | `GET /workspaces` |
| `/workspaces/new` | — |
| `/workspaces/[wsId]` | `GET /workspaces/{wsId}`, `GET /workspaces/{wsId}/documents`, `GET /workspaces/{wsId}/agents` |
| `/workspaces/[wsId]/agents/new` | `GET /workspaces/{wsId}` (ready-doc count for the gate) |
| `/workspaces/[wsId]/agents/[agentId]` | `GET .../agents/{agentId}`, `GET .../agents/{agentId}/tokens`, `GET .../agents/{agentId}/conversations` |
| `.../conversations/[convId]` | `GET .../conversations/{convId}` |
| `/account` | session info held in memory |

---

## 4. Page-by-Page Specification

Fifteen pages. Every one has an explicit spec.

---

### 4.1 Login — `/login`

- **Purpose:** exchange credentials for a JWT and start a session.
- **Data on load:** none. If a valid in-memory token already exists, redirect to `/dashboard`.
- **Components:** `AuthShell` (split layout), `Input` ×2 (email, password), password visibility
  toggle, `Button` (primary, loading), inline `FormError`, link to `/register`, link to "Forgot
  password?" (marked *coming soon* — no backend endpoint exists; do not build a dead form).
- **Actions:** submit, toggle password visibility, navigate to `/register`.
- **Validation:** email format; password non-empty (do not enforce min-8 on login — it is not the
  user's password being created).
- **Empty state:** n/a.
- **Loading:** button spinner + disabled inputs.
- **Errors:** `401` → "Invalid email or password" as a single form-level message (do not reveal
  which field was wrong). `422` → map to fields. Network failure → toast + inline retry.
- **Success feedback:** store JWT, redirect to `/dashboard`.

---

### 4.2 Register — `/register`

- **Purpose:** create an account and sign in.
- **Data on load:** none.
- **Components:** as Login plus password requirement hint ("At least 8 characters"), a Terms
  checkbox (visual only — no backend field), right-hand brand panel.
- **Actions:** submit, navigate to `/login`.
- **Validation:** email format, password ≥ 8 chars, terms checked. Show a live strength hint
  (not a blocking meter).
- **Errors:** `400 "Email already registered"` → inline under email + "Log in instead?" link.
  `422` → per-field. `5xx` → toast.
- **Success feedback:** store JWT → `/dashboard`. The first dashboard visit shows onboarding.

---

### 4.3 Dashboard — `/dashboard`

- **Purpose:** answer "what is my bot doing right now" and drive the next action.
- **Data on load:** `GET /workspaces`. If any exist, also `GET .../agents` and `.../documents` for
  each (N+1 — acceptable for the expected ≤ 10 workspaces; note this for a future summary endpoint).
- **Components:** `PageHeader`, `OnboardingChecklist` (3 cards), `StatCard` ×4, `WorkspaceCard`
  list, `AgentCard` list (recent 5), `ActivityFeed`, `Button`.
- **Stat cards:** Workspaces · Agents (active) · Ready documents · Widget requests (sum of
  `request_count` across tokens — requires fetching all agents' tokens; if that is too many calls,
  omit this card rather than shipping a wrong number).
- **Actions:** create workspace, create agent, upload document, open workspace, open agent.
- **Validation:** n/a.
- **Empty state (no workspaces):** full-width onboarding checklist, primary CTA "Create your first
  workspace".
- **Loading:** `LoadingSkeleton` ×4 stat cards + 3 agent cards. Never a spinner over the whole page.
- **Errors:** if `GET /workspaces` fails → full-page error block with "Retry" and the status code.
  Partial failures (agents load failed) → degrade gracefully: stat cards show `—`.
- **Success feedback:** quick-create toasts.

---

### 4.4 Workspaces list — `/workspaces`

- **Purpose:** see and switch between knowledge bases.
- **Data on load:** `GET /workspaces`.
- **Components:** `PageHeader`, `WorkspaceCard` grid, `Button`, `SearchInput` (client-side filter),
  `EmptyStateBlock`, `SkeletonGrid`.
- **Actions:** create, open, edit (→ settings tab), delete (confirm).
- **Validation:** n/a.
- **Empty state:** "No workspaces yet." + explanation ("A workspace holds your documents and the
  agents built from them.") + primary CTA "Create workspace".
- **Loading:** 3 skeleton cards.
- **Errors:** full-page error block.
- **Success feedback:** create → toast + navigate to the new workspace.

---

### 4.5 Create workspace — `/workspaces/new`

- **Purpose:** create a knowledge base.
- **Data on load:** none.
- **Components:** `FormShell`, `Input` (name), `Textarea` (description), `Textarea` (system prompt,
  prefilled with the API default), `Button`, `Breadcrumb`.
- **Actions:** submit, cancel (→ `/workspaces`).
- **Validation:** name required, 1–100 chars. Show `n/100` counter.
- **Empty state:** n/a.
- **Loading:** submit button spinner.
- **Errors:** `422` → per-field. `401` → global 401 flow.
- **Success feedback:** toast "Workspace created" → redirect `/workspaces/[wsId]`.

---

### 4.6 Workspace detail — `/workspaces/[wsId]` (tabs: Documents / Agents / Settings)

- **Purpose:** the main container for a workspace's knowledge and agents.
- **Data on load:** `GET /workspaces/{wsId}`, `GET .../documents`, `GET .../agents`.
- **Components:** `PageHeader` (name + description + tabs), `FileUploadZone`, `DocumentTable`,
  `TrainingStatusIndicator`, `AgentCard` grid, `EmptyStateBlock`, `ConfirmationDialog`, `Badge`.
- **Tab persistence:** store the active tab in the URL query (`?tab=`) so links are shareable and the
  browser Back button works. This is not optional.
- **Actions:** upload (drag/drop or picker), train, retry failed training, delete document, create
  agent, edit agent, delete agent, rename workspace, delete workspace.
- **Validation:** upload extension ∈ `.pdf/.txt/.docx`; recommend ≤ 50 MB client-side.
- **Empty states:**
  - Documents: "No documents yet." + "Upload your first document to give your agents knowledge." +
    upload zone highlighted.
  - Agents: "No agents yet." + **New agent** button — **disabled** with tooltip if no document is
    `ready`, per [§9.7](#97-disabled-states-for-unmet-prerequisites).
- **Loading:** document table skeleton rows (keep the upload zone interactive so the user is never
  blocked); agent card skeletons.
- **Errors:** `404 "Workspace not found"` → render a dedicated "Workspace not found" page with a link
  back to `/workspaces` (do not show a generic error). `401` → global flow. `400` on upload → mark the
  affected row.
- **Success feedback:** upload → optimistic row; train → `processing` badge; delete → toast +
  row removal; workspace delete → toast + redirect.

---

### 4.7 Agent create — `/workspaces/[wsId]/agents/new`

- **Purpose:** define an agent's persona over the workspace knowledge.
- **Data on load:** `GET /workspaces/[wsId}` (+ documents count) to evaluate the prerequisite gate.
- **Components:** `FormShell`, `Input` (name), `Textarea` (description), `Textarea` (system prompt),
  `Textarea` (welcome message + counter), `Select` (model), `RangeSlider` (temperature),
  `Select` (language), `Button`, `InfoCallout`, `Breadcrumb`.
- **Actions:** submit, cancel, reset-to-defaults.
- **Validation:** name 1–100; system_prompt ≥ 1; welcome_message ≤ 500; temperature clamp 0–1.
- **Empty state:** if the gate is unmet, replace the form with a blocking empty state: an icon, the
  explanation, and a link to the Documents tab. Do not render a disabled form.
- **Loading:** submit spinner.
- **Errors:** `422` per-field; `404` → workspace/agent not found page.
- **Success feedback:** toast "Agent created" → `/workspaces/[wsId]/agents/[agentId]`.

---

### 4.8 Agent detail — `/workspaces/[wsId]/agents/[agentId]` (tabs: Overview / Test / Conversations / Embed)

- **Purpose:** configure, test, monitor and deploy one agent.
- **Data on load:** `GET .../agents/{agentId}`, `GET .../agents/{agentId}/tokens`,
  `GET .../agents/{agentId}/conversations`. Fetch per active tab only — do not load conversation
  bodies on the Overview tab.
- **Components:** `PageHeader` (agent name, `is_active` toggle, status), `TabNav`, `DefinitionList`,
  `ChatPreviewPanel`, `ConversationTable`, `EmbedTokenTable`, `CodeSnippetDisplay`,
  `Toggle`, `Badge`, `ConfirmationDialog`, `Button`.
- **Actions:** edit any config field (inline save or "Edit" → form), toggle active, test chat,
  create/revoke/edit/delete token, copy snippet, open/delete conversation, delete agent.
- **Validation:** same as create, applied per field on save.
- **Empty states:** Conversations → "No conversations yet." + "Start a conversation". Embed → "No
  embed tokens yet." + "Create your first embed token" + a one-line explanation of what a token is.
- **Loading:** overview → definition-list skeleton; each tab lazy-loads with its own skeleton.
- **Errors:** `404 "Agent not found"` → dedicated not-found page. `403` → this can occur if the
  agent's workspace is not owned; show "You don't have access to this agent."
- **Success feedback:** inline "Saved" tick on config save (optimistic, no toast for autosave); toast
  for destructive and token actions.

---

### 4.9 Agent chat preview — `/workspaces/[wsId]/agents/[agentId]?tab=test`

- **Purpose:** validate the agent before embedding.
- **Data on load:** `GET .../agents/{agentId}` for name/welcome/language. Optionally the most recent
  conversation so a refresh does not lose the thread.
- **Components:** `ChatMessageBubble` (user/assistant/error), `TypingIndicator`, `ChatInput`,
  `SourceChips`, `CitationGroundingWarning`, `Button` (New conversation), `PanelHeader`.
- **Actions:** send, clear/new conversation, copy answer text.
- **Validation:** message 1–4000 characters; show a counter that turns amber at 3800 and red at
  4000; Enter sends, Shift+Enter newline.
- **Empty state:** before the first message, show a centred greeting bubble rendered from
  `welcome_message` (the API returns it), plus 3–4 suggested starter questions as clickable chips
  derived from the agent's documents if you can infer them client-side — otherwise a generic set.
- **Loading:** typing indicator on every in-flight turn.
- **Errors:** `200` with `sources: []` → amber grounding warning, not an error. `403` (revoked
  agent) → inline "This agent is inactive." `429` → "You're sending messages too fast."
  `5xx` → error bubble, retry affordance.
- **Success feedback:** no toast — the answer appearing is the feedback.

---

### 4.10 Conversations list — `.../agents/[agentId]?tab=conversations`

- **Purpose:** review what visitors asked.
- **Data on load:** `GET .../conversations`.
- **Components:** `DataTable` (title, updated, actions), `RelativeTime`, `EmptyStateBlock`,
  `Button`, `ConfirmationDialog`, `SearchInput` (client-side).
- **Actions:** open thread, delete, search/filter client-side, start new conversation.
- **Validation:** n/a.
- **Empty state:** "No conversations yet." + "Start a conversation" → Test tab.
- **Loading:** 5 skeleton rows.
- **Errors:** `404` → not-found page; `5xx` → table-level error with Retry.
- **Success feedback:** delete → toast "Conversation deleted" + optimistic row removal.

---

### 4.11 Conversation thread — `.../agents/[agentId]/conversations/[convId]`

- **Purpose:** read one stored conversation in full.
- **Data on load:** `GET .../conversations/{convId}` → `{ conversation, messages }`.
- **Components:** `Breadcrumb`, `ChatMessageBubble` (read-only), `SourceChips`, `RelativeTime`,
  `Button` (delete, back), `InfoBanner`, `CopyButton`.
- **Actions:** back, delete, copy a message.
- **Validation:** n/a.
- **Empty state:** if `messages` is empty (conversation created but never used), show "This
  conversation has no messages yet."
- **Loading:** bubble skeletons for ~6 messages.
- **Errors:** `404 "Conversation not found"` → dedicated not-found state.
- **Success feedback:** delete → toast + navigate back to the list.

---

### 4.12 Embed tokens — `.../agents/[agentId]?tab=embed`

- **Purpose:** create, monitor and revoke the credentials that let a website talk to this agent.
- **Data on load:** `GET .../tokens`.
- **Components:** `DataTable`, `Toggle` (is_active), `OriginChipInput`, `Modal` (create/edit),
  `CodeSnippetDisplay` + `CopyButton`, `StatCard` (total requests), `RelativeTime`,
  `ConfirmationDialog`, `AlertBanner` (for the one-time token warning), `Button`.
- **Actions:** create token, edit label/origins, toggle active, copy snippet, delete token, "Test it".
- **Validation:** label required 1–100. Origins must be bare hostnames — strip any `https://`,
  trailing `/`, or path **client-side** before sending, and reject values containing `/` or `:` with
  a clear message.
- **Empty state:** "No embed tokens yet." + one-line explanation ("An embed token is the key that
  lets your website talk to this agent.") + primary CTA.
- **Loading:** skeleton rows.
- **Errors:** `404` on any token call → agent not found page. `400` → toast with the server message.
- **Success feedback:** create → the mandatory one-time token modal; copy → button state change;
  revoke → toast with the consequence spelled out; delete → toast.

---

### 4.13 Snippet view — `.../agents/[agentId]?tab=embed&snippet=[tokenId]`

- **Purpose:** show the exact code the merchant must paste, with the full token.
- **Data on load:** `GET .../tokens/{tokenId}/snippet` → `{ snippet, token }`. **`token` here is the
  FULL value**, not masked.
- **Components:** `CodeSnippetDisplay` (syntax-highlighted), `CopyButton` (with copied state),
  `Tabs` (HTML / JavaScript setup note), `StepChecklist`, `Button` ("Test it", opens the referrer in
  a new tab), `AlertBanner`.
- **Actions:** copy code, copy token alone, mark steps complete, open test page.
- **Validation:** n/a.
- **Empty state:** n/a — if the token id is invalid, `404` → inline "Token not found" with a link
  back to the token list.
- **Loading:** code-block skeleton (fixed height to avoid layout shift — this matters, the code block
  must not reflow when it arrives).
- **Errors:** `404` → inline not-found. `401` → global flow.
- **Success feedback:** copy → "Copied" for 2 s (see [§9.5](#95-toast-duration-and-placement)).

---

### 4.14 Workspace settings — `/workspaces/[wsId]?tab=settings`

- **Purpose:** rename, edit the default system prompt, or delete the workspace.
- **Data on load:** `GET /workspaces/{wsId}`.
- **Components:** `FormShell`, `Input`, `Textarea`, `Button` (Save), `DangerZone` (delete
  workspace), `ConfirmationDialog`.
- **Actions:** save changes, delete workspace.
- **Validation:** name required 1–100.
- **Empty state:** n/a.
- **Loading:** skeleton form.
- **Errors:** `404` → not-found page; `422` per-field.
- **Success feedback:** "Saved" tick; delete → toast + redirect to `/workspaces`.
- **Note:** the `Workspace` object has **no `updated_at`** — do not render a "last updated" field.

---

### 4.15 Account — `/account`

- **Purpose:** show session identity and provide logout. There is no profile-editing backend.
- **Data on load:** none — everything shown comes from the in-memory session (email, user_id).
- **Components:** `ProfileCard`, `InfoRow` (email, user ID, token expiry), `Button` (Log out),
  `InfoCallout`.
- **Actions:** log out.
- **Validation:** n/a.
- **Empty state:** n/a.
- **Loading:** n/a.
- **Errors:** if the session is already invalid, render the logged-out variant.
- **Success feedback:** logout → clear in-memory token → `/login`.

---

## 5. Component Library

Every component below is required. Names match the folder structure in [§11](#11-folder-structure).

### 5.1 Button

- **Purpose:** all clickable actions.
- **Props:** `variant`, `size`, `loading`, `disabled`, `iconLeft`, `iconRight`, `href`, `type`,
  `onClick`, `fullWidth`.
- **Variants:** `primary` (indigo fill), `secondary` (surface + border), `ghost` (transparent,
  hover surface), `danger` (red fill), `dangerGhost` (red text + border), `link`.
- **Sizes:** `sm` (32px), `md` (38px), `lg` (44px — auth pages only).
- **States:** default, hover, active, focus-visible (2px ring, never remove), disabled (50% opacity,
  `cursor: not-allowed`), loading (spinner replaces icon, width locked to prevent layout shift).
- **Used on:** every page. `primary` for the single main action per view.

### 5.2 Input

- **Purpose:** single-line text entry.
- **Props:** `label`, `value`, `onChange`, `type`, `placeholder`, `error`, `hint`, `required`,
  `disabled`, `autoComplete`, `maxLength`, `showCounter`, `prefixIcon`, `endAdornment`.
- **States:** default, focus (indigo border + ring), error (red border + red message), disabled,
  read-only.
- **Used on:** login, register, workspace form, token label, search inputs.
- **Note:** wire `autoComplete="email"` / `"current-password"` / `"new-password"`.

### 5.3 Textarea

- **Purpose:** multi-line entry with optional counter.
- **Props:** as Input, plus `rows`, `autoResize`.
- **States:** as Input, plus focus.
- **Used on:** system prompt, welcome message (with 500-char counter), workspace description.

### 5.4 Select / Dropdown

- **Purpose:** constrained single-select (model, language).
- **Props:** `options: {value,label,group?,disabled?}[]`, `value`, `onChange`, `label`, `error`,
  `hint`, `disabled`, `placeholder`.
- **States:** default, open, focus, selected, disabled, error.
- **Used on:** agent create/edit (model, language).
- **Note:** the model dropdown **must** mark paid-tier options and explain the cost difference —
  see [§6.7](#67-model-dropdown-reference-data).

### 5.5 RangeSlider

- **Purpose:** temperature 0.0–1.0.
- **Props:** `min=0`, `max=1`, `step=0.1`, `value`, `onChange`, `label`, `valueFormatter`,
  `captionFor` (maps a value to a plain-language caption).
- **Used on:** agent create/edit.
- **Note:** keyboard accessible — arrow keys adjust, `role="slider"`, `aria-valuenow`.

### 5.6 OriginChipInput

- **Purpose:** enter allowed origins as chips.
- **Props:** `value: string[]`, `onChange`, `placeholder`, `maxChips`.
- **Behaviour:** Enter or comma commits a chip; Backspace on an empty input removes the last chip;
  pasting `https://x.com, https://y.com` splits into multiple chips; a chip containing `/`, `:` or
  whitespace is rejected inline (normalise first — strip protocol, trailing slash, and path).
- **Used on:** token create/edit modal.

### 5.7 Modal

- **Purpose:** focused confirmations and forms.
- **Props:** `open`, `onClose`, `title`, `description`, `size` (`sm` 400px / `md` 560px / `lg` 720px),
  `footer`, `closeOnOverlay`, `dismissible`.
- **States:** closed, opening, open, closing. Trap focus on open, restore on close, `Esc` to close,
  overlay click closes only when `dismissible`.
- **Used on:** create/edit token, delete confirmations, one-time token display.

### 5.8 ConfirmationDialog

- **Purpose:** mandatory gate before destructive actions.
- **Props:** `open`, `title`, `body` (ReactNode — may list consequences as a `<ul>`), `confirmLabel`,
  `cancelLabel`, `variant` (`danger` / `default`), `onConfirm`, `confirmLoading`.
- **Used on:** delete document, delete agent, delete workspace, delete conversation, delete token,
  revoke token. Exact copy is mandated in [§9.4](#94-mandatory-confirmation-dialogs).

### 5.9 Toast / Notification

- **Purpose:** transient feedback for non-blocking outcomes.
- **Props:** `variant` (`success` / `error` / `warning` / `info`), `title`, `description`, `action`,
  `duration`.
- **States:** entering, visible, leaving. Stacked, newest at the bottom-right (or top-centre on
  mobile). `role="status"` for success/info, `role="alert"` for error/warning.
- **Used on:** all mutations. Never for field validation.

### 5.10 Badge

- **Purpose:** compact status label. The four document statuses are fixed values — see
  [§7.8](#78-document-status-badges).
- **Props:** `tone` (`neutral` / `info` / `warning` / `success` / `danger` / `accent`), `size`,
  `dot`, `animated`, `icon`, `children`.
- **Used on:** document status rows, agent status, token status, origins count.

### 5.11 FileUploadZone

- **Purpose:** drag-and-drop upload with pre-flight validation.
- **Props:** `accept`, `maxSizeMb`, `multiple`, `onFiles`, `disabled`, `uploadingCount`.
- **States:** idle, drag-over (indigo dashed border + tinted background), uploading (progress per
  file), error (per-file message), complete (brief success flash).
- **Used on:** workspace Documents tab.

### 5.12 TrainingStatusIndicator

- **Purpose:** represent a document's training lifecycle and own the poll loop.
- **Props:** `status` (`uploaded` / `processing` / `ready` / `failed`), `chunkCount`, `onRetry`,
  `pollIntervalMs` (default `3000`).
- **Behaviour:** renders a badge per [§7.8](#78-document-status-badges) plus, while `processing`, a
  looping indeterminate progress bar and "Training… ~Ns". Starts/stops its own polling per
  [§6.4](#64-document-training-poll-loop).
- **Used on:** workspace Documents tab rows.

### 5.13 ChatMessageBubble

- **Purpose:** render one message.
- **Props:** `role` (`user` / `assistant` / `error`), `content`, `sources`, `createdAt`, `modelUsed`,
  `isPending`, `onRetry`, `onCopy`, `readOnly`.
- **States:** user (right-aligned, indigo), assistant (left-aligned, surface), error (left-aligned,
  red, with a Retry action), pending (typing dots), ungrounded (assistant + `sources: []` → amber
  left border).
- **Used on:** agent Test tab, conversation thread view.
- **Note:** render `content` as **plain text** (never `dangerouslySetInnerHTML`); use
  `white-space: pre-wrap` so the LLM's line breaks survive.

### 5.14 ChatInput

- **Purpose:** message composer.
- **Props:** `value`, `onChange`, `onSend`, `disabled`, `placeholder`, `maxLength=4000`,
  `showCounter`, `autoFocus`.
- **Behaviour:** Enter sends, Shift+Enter inserts a newline, `Esc` closes the panel (Test tab only),
  counter appears at 80% of the limit.
- **Used on:** agent Test tab.

### 5.15 SourceChips

- **Purpose:** render `sources[]` beneath an answer.
- **Props:** `sources`, `variant` (`inline` for chat, `block` for thread view).
- **Behaviour:** one chip per source showing `filename` (plus `chunk_index` when present). If the
  array is empty, render the grounding warning instead — never an empty row.
- **Used on:** `ChatMessageBubble`.

### 5.16 AgentCard

- **Purpose:** summarise one agent in a grid.
- **Props:** `agent`, `onOpen`, `onTest`, `onToggleActive`, `readyDocumentCount`.
- **Contents:** name, description (2-line clamp), active dot, language, model label, "Test" and
  "Embed" quick actions, relative `created_at`.
- **States:** default, inactive (desaturated + "Inactive" badge), menu-open.
- **Used on:** workspace Agents tab, dashboard recent agents.

### 5.17 WorkspaceCard

- **Purpose:** summarise one workspace in the switcher and on `/workspaces`.
- **Props:** `workspace`, `stats` (`{agents, readyDocuments}`), `onOpen`, `onEdit`, `onDelete`.
- **Contents:** name, description, stats row, relative `created_at`, overflow menu.
- **Used on:** `/workspaces`, dashboard.

### 5.18 SidebarNavigation

- **Purpose:** primary navigation.
- **Props:** `items`, `activeRoute`, `collapsed`, `onToggleCollapse`, `footer`.
- **Contents:** logo/wordmark, workspace switcher at the top, then Dashboard / Workspaces / Account,
  with active-route indication and a collapsible rail on tablet.
- **States:** expanded, collapsed (icon-only, 64px), mobile-drawer (overlay).
- **Used on:** every authenticated page.

### 5.19 TopNavigationBar

- **Purpose:** context and global actions.
- **Props:** `breadcrumbs`, `actions`, `onOpenCommandPalette`.
- **Contents:** `Breadcrumb`, page-level primary action slot, help link, account avatar menu
  (profile, security, log out).
- **Used on:** every authenticated page.

### 5.20 Breadcrumb

- **Purpose:** show hierarchy.
- **Props:** `items: {label, href?}[]`, `maxItems`.
- **Behaviour:** truncate from the left with an overflow menu past 4 items; the last item is current
  and is not a link; current item gets `aria-current="page"`.
- **Used on:** TopNavigationBar, detail pages, thread view.

### 5.21 EmptyStateBlock

- **Purpose:** the single pattern for "nothing here yet".
- **Props:** `icon`, `title`, `description`, `action`, `actionVariant`, `secondaryAction`, `size`,
  `illustration`.
- **Rule:** one empty-state composition per section; copy is mandated in
  [§9.6](#96-empty-state-copy-mandated).
- **Used on:** every list page.

### 5.22 ConfirmationDialog

See [§5.8](#58-confirmationdialog).

### 5.23 CodeSnippetDisplay

- **Purpose:** show the embed snippet with copy.
- **Props:** `code`, `language` (`html`), `filename`, `copyLabel`, `onCopy`, `wrap`.
- **Behaviour:** syntax-highlighted, dark code block, monospace, a copy button in the top-right of
  the block whose icon swaps to a check for 2 s on success. `wrap` off by default (code must not
  reflow); provide a "toggle wrap" affordance for narrow screens.
- **Used on:** embed snippet view, token row "copy snippet".

### 5.24 Toggle

- **Purpose:** boolean switch for `is_active`.
- **Props:** `checked`, `onChange`, `label`, `description`, `disabled`, `size`, `loading`.
- **States:** on (accent track + knob), off (neutral track), focus-visible, disabled, loading.
- **Rule:** always pair with a text label. Colour alone must not carry meaning
  (`aria-checked` + visible label). See [§7.9](#79-agent-and-token-active-toggles).
- **Used on:** token table rows, agent header.

### 5.25 LoadingSkeleton

- **Purpose:** placeholder content during fetch.
- **Props:** `variant` (`text` / `circle` / `rect` / `card` / `table` / `code`), `rows`, `width`,
  `height`.
- **Behaviour:** shimmer animation, `aria-hidden="true"`, and the container carries
  `aria-busy="true"`. Skeletons must roughly match final dimensions to avoid layout shift — critical
  for the code block and chat log.
- **Used on:** every loading state.

### 5.26 AlertBanner / InfoCallout

- **Purpose:** inline persistent messaging (not transient).
- **Props:** `tone` (`info` / `warning` / `danger` / `success`), `title`, `children`, `action`,
  `icon`.
- **Used on:** the one-time token warning, the "no documents yet" agent gate, grounding warnings,
  read-only banners in the thread view, CORS/dev hints.

### 5.27 DataTable

- **Purpose:** the shared list primitive.
- **Props:** `columns`, `rows`, `rowKey`, `emptyState`, `loading`, `onSortChange`, `stickyHeader`,
  `rowActions`.
- **Behaviour:** responsive — below 768px each row becomes a stacked card with the column labels as
  captions. Support client-side sort only; **the API has no pagination or sorting**, so never render
  a paginator (see [§9.10](#910-pagination--there-isnt-any)).
- **Used on:** documents, conversations, tokens.

### 5.28 DefinitionList

- **Purpose:** read-only key/value display of a config object.
- **Props:** `items: {label, value, mono?, copyable?}[]`, `columns`.
- **Used on:** agent Overview tab, account page, snippet context.

### 5.29 RelativeTime

- **Purpose:** "3 minutes ago" with an absolute title tooltip.
- **Props:** `date`, `live` (auto-refresh), `format`.
- **Used on:** documents, conversations, tokens, agents.

### 5.30 StatCard

- **Purpose:** a single headline metric.
- **Props:** `label`, `value`, `delta`, `icon`, `tone`, `loading`, `href`.
- **Used on:** dashboard, embed tab.

---

## 6. API Integration Guide

### 6.1 Error shape normalisation

`detail` is **polymorphic** and the frontend must handle all three cases:

| Case | Body | Where it happens |
|---|---|---|
| String | `{"detail":"Workspace not found"}` | 400, 401, 403, 404, 409, 500 |
| Array | `{"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}` | 422 validation |
| Object | `{"detail":{"errors":{...}}}` | rare; treat generically |

Implement one helper and use it everywhere:

```ts
// lib/api-error.ts
export type FieldIssue = { field: string; message: string };

export function normaliseError(body: unknown, status: number): {
  message: string; fieldErrors: FieldIssue[];
} {
  const detail = (body as any)?.detail;

  if (Array.isArray(detail)) {
    const fieldErrors = detail.map((d: any) => ({
      // loc is e.g. ["body","name"] -> take the last segment
      field: Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "form",
      message: d.msg ?? "Invalid value",
    }));
    return { message: "Please check the highlighted fields.", fieldErrors };
  }

  if (typeof detail === "string") return { message: detail, fieldErrors: [] };

  // 401 fallback — the API's message may be missing
  if (status === 401) return { message: "Your session has expired. Please sign in again.", fieldErrors: [] };

  return { message: "Something went wrong. Please try again.", fieldErrors: [] };
}
```

Rules:
- Never show a raw `detail` string to a user if it is a technical message. Maintain a map of
  known-good messages to friendly copy, and fall back to generic copy.
- For 422, always map to fields — never show the raw array.
- Network failure (fetch rejects / timeout) → `message: "Cannot reach the server."`

### 6.2 JWT storage and the 401 flow

**Decision: hold the token in memory only. Do not use `localStorage`, `sessionStorage` or a cookie.**

Rationale: any token in `localStorage` is readable by any XSS payload and survives indefinitely; this
is a B2B dashboard holding merchant data. The trade-off is that a hard refresh loses the session,
which we mitigate with the flow below.

Implementation:

```ts
// lib/auth.ts — module-level, not persisted
let token: string | null = null;
let user: { userId: string; email: string } | null = null;

export const auth = {
  get: () => token,
  getUser: () => user,
  set: (t: string, u: { userId: string; email: string }) => { token = t; user = u; },
  clear: () => { token = null; user = null; },
};
```

**Token lifetime:** the backend issues a JWT valid for **7 days** (`ACCESS_TOKEN_EXPIRE_DAYS=7`).
The payload contains only `sub` and `exp` — there is **no `iat`** and no refresh token, so you cannot
reliably read "time remaining" client-side.

**Mandatory 401 handling.** Every authenticated request goes through one wrapper. On any `401`
("Invalid or expired token"):

1. `auth.clear()`
2. Show a toast: **"Your session expired. Please sign in again."** (4 s, `warning`)
3. `router.replace('/login?redirect=' + encodeURIComponent(currentPath))`
4. The login page reads `redirect` and returns the user there after success. Default `/dashboard`.
5. **Deduplicate:** if several requests 401 concurrently, only the first should trigger the redirect
   (a module-level `handling401` flag). Otherwise the user sees a toast storm and racing pushes.

```ts
let redirecting = false;
if (res.status === 401 && !redirecting) {
  redirecting = true;
  auth.clear();
  toast.warning("Your session expired. Please sign in again.");
  router.replace(`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`);
}
```

Route guard: any protected route renders **nothing** until the auth check resolves, then redirects to
`/login` if there is no token. Avoid a flash of the login page.

### 6.3 Attaching the token

```ts
// lib/api-client.ts
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL!;

export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const t = auth.get();
  const res = await fetch(BASE + path, {
    ...opts,
    headers: {
      ...(opts.body && !(opts.body instanceof FormData)
        ? { "Content-Type": "application/json" } : {}),
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error("api"), { status: res.status, body });
  return body as T;
}
```

Rules: **never** set `Content-Type` manually for `FormData` (it must keep the boundary). Always
`await res.json().catch(() => ({}))` — some error paths return non-JSON.

### 6.4 Document training poll loop

Trigger: on page load, and after any `202` from `train`.

```ts
// 3 s interval. Stop on terminal state, on 404, or on unmount.
function useTrainingPoll(workspaceId: string, docId: string, onUpdate: (s: DocumentStatus) => void) {
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (!alive) return;
      try {
        const s = await api<DocumentStatus>(`/workspaces/${workspaceId}/documents/${docId}/status`);
        onUpdate(s);
        if (s.status === "ready" || s.status === "failed") return;   // terminal -> stop
      } catch { /* transient network error: let the next tick retry */ }
      if (alive) timer = setTimeout(tick, 3000);
    };
    let timer = setTimeout(tick, 3000);
    return () => { alive = false; clearTimeout(timer); };
  }, [workspaceId, docId]);
}
```

Mandatory behaviour:

| Rule | Detail |
|---|---|
| Interval | **3000 ms** |
| Start | After `train` returns `202`, and on page load for any document not yet terminal |
| Stop when | `status` is `"ready"` **or** `"failed"` |
| Stop also on | `404` (document deleted elsewhere), route unmount, workspace switch |
| Never stop early on | `409`, `5xx`, or a network error — retry on the next tick |
| `200` from `train` | Means already `ready`. **Do not start polling.** |
| On `ready` | Refresh the document list (new chunk counts may change agent gating) and show a single toast |
| On `failed` | Stop, red badge, Retry button calling `train` again |
| Cap | If `processing` persists > 10 minutes, stop polling and show "Taking longer than expected — check back shortly." Do not poll forever. |
| Duplication | One poller per document id. The token list's `409` path must not create a second poller. |

Only one "Training complete" toast per document even if several components observe the transition —
track it in the list state, not in the poller.

### 6.5 The embed token: full value shown exactly once

`POST .../tokens` → `201` is the **only** response that ever contains the untruncated token. `GET
.../tokens` and `GET .../tokens/{id}` return `"a3f7c91b..."` (11 chars: 8 + `...`).
`GET .../tokens/{id}/snippet` also returns the full token in its `token` field.

Frontend requirements:

1. On `201`, immediately open a **modal** — do not navigate away, do not render it in a toast.
2. The modal must contain:
   - A `warning` `AlertBanner`:
     > **Copy this token now.** For your security we only show it once. If you lose it, delete this
     > token and create a new one — we cannot recover it for you.
   - The token in a monospace `CodeSnippetDisplay` with a **Copy token** button.
   - The **full embed snippet** with a **Copy snippet** button (the snippet already contains the
     token, so this is the primary action).
   - A 3-step checklist: copy → paste before `</body>` → verify on the live site.
   - Primary button "I've copied it" → closes the modal.
   - **Dismissal guard:** if the user closes the modal via overlay or Esc **without** copying, re-open
     it once with a stronger warning. Track `copied` state; never silently discard the only copy.
3. Never store the full token in a global store, localStorage, or a URL. Keep it in component state
   for the lifetime of the modal only, then null it.
4. The token table shows the masked value from the API plus the `label`. If the user needs the full
   token again, call `GET .../tokens/{id}/snippet` on demand.
5. **Never log the full token** to console, analytics, or an error reporter.

### 6.6 Agent chat `conversation_id` lifecycle

```
let conversationId: string | null = null;   // starts null

// turn 1
POST /workspaces/{ws}/agents/{agent}/chat   { message }                    // omit conversation_id when null
→ 200 { conversation_id, answer, sources, model_used }
  conversationId = data.conversation_id;     // STORE IMMEDIATELY

// turn 2..n
POST /workspaces/{ws}/agents/{agent}/chat   { message, conversation_id }
→ 200 { conversation_id, ... }              // same id back; keep it

// "New conversation"
POST /workspaces/{ws}/agents/{agent}/conversations/new   → 201 Conversation
  conversationId = conversation.id;  clear the message list
```

Notes:
- The first request may **omit** `conversation_id` entirely (the field is optional/null). Sending
  `null` is also accepted. Omitting is cleaner.
- `conversations/new` returns **201**, not 200.
- A freshly created conversation is titled `"New Conversation"`; the backend auto-titles it from the
  **first user message**, so expect the title to change after turn 1 — this is normal, do not treat
  it as a bug.
- Errors do not clear `conversationId`.
- `sources` is `[]` when nothing is retrieved — not an error.

### 6.7 Model / language dropdown reference data

**There is no API endpoint that lists models or languages** (`/api/v1/query/llm/status` requires an
`X-API-Key` and is not for the dashboard). These lists must be hardcoded and kept in sync with the
backend. Verified against the running server:

| Model id | Tier | Label | Status |
|---|---|---|---|
| `meta-llama/llama-3.1-8b-instruct` | **paid** | Llama 3.1 8B Instruct | ✅ working — **this is the server default** |
| `openrouter/auto` | **paid** | OpenRouter Auto | ✅ working (auto-routes to an available model) |
| `meta-llama/llama-3.3-70b-instruct:free` | free | Llama 3.3 70B Instruct | ⚠️ currently 404 — unavailable for free |
| `qwen/qwen3-235b-a22b:free` | free | Qwen3 235B A22B | ⚠️ currently 404 — deprecated upstream |
| `google/gemma-3-27b-it:free` | free | Gemma 3 27B IT | ⚠️ currently 404 — unavailable for free |
| `openrouter/free` | free | OpenRouter Auto (free) | ⚠️ subject to a daily free-request quota |

> **Critical for the designer and developer.** All free-tier models were unusable at the time of
> writing (404s / quota exhaustion), which is why the server default was moved to a **paid** model.
> Free options are still selectable and may recover. The model dropdown **must**:
> - default to `meta-llama/llama-3.1-8b-instruct` (matching the server),
> - group options under "Paid" and "Free (limited availability)",
> - show a caption under the dropdown naming the current billing implication, e.g.
>   *"Paid models give reliable answers. Free models may be rate-limited or temporarily
>   unavailable."*
>
> The agent's `model` value is **always echoed in `model_used`** on a successful chat, which is how
> you debug a model problem without server logs.

**Languages** (hardcoded, `maxLength=50`, default `English`):
`English`, `Swahili`, `French`, `Arabic`, `Portuguese`.

> Any other value is accepted by the API but **silently coerced to `English`** by the backend's
> config validator. Constrain the dropdown to these five so the UI and stored value never disagree.

### 6.8 TypeScript types (copy these)

```ts
export type ISODate = string;

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user_id: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  owner_id: string;
  created_at: ISODate;
  // NOTE: no updated_at on Workspace
}

export type DocStatus = "uploaded" | "processing" | "ready" | "failed";
export type FileType = "pdf" | "txt" | "docx";

export interface WorkspaceDocument {
  id: string;
  workspace_id: string;
  filename: string;
  file_type: FileType;
  size_bytes: number;
  status: DocStatus;
  chunk_count: number;
  created_at: ISODate;
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  model: string;
  temperature: number;
  language: string;
  /** NOTE: returned as the NUMBER 0 | 1, not a boolean. */
  is_active: 0 | 1;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Conversation {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: unknown[] | null;
  created_at: ISODate;
}

export interface Source { filename: string; chunk_index: number }

export interface AgentChatResponse {
  conversation_id: string;
  answer: string;
  sources: Source[];      // may be []
  model_used: string;
}

export interface WorkspaceChatResponse {
  answer: string;
  sources: Source[];      // may be []
  conversation_history: { role: "user" | "assistant"; content: string }[];
}

export interface ConversationThread {
  conversation: Conversation;
  messages: Message[];
}

export interface EmbedToken {
  id: string;
  agent_id: string;
  /** "a3f7c91b..." — masked on list/get; full only on create and /snippet */
  token: string;
  label: string;
  /** NOTE: returned as a BOOLEAN on embed tokens (unlike Agent.is_active which is 0|1). */
  is_active: boolean;
  allowed_origins: string[] | null;   // null = any origin allowed
  request_count: number;
  created_at: ISODate;
  last_used_at: ISODate | null;
}

export interface EmbedSnippet {
  snippet: string;   // full HTML embed code, contains the full token
  token: string;     // full token
}

export interface PublicAgentInfo {
  name: string;
  description: string;
  language: string;
  welcome_message: string;
}
```

### 6.9 Endpoint-by-endpoint integration table

| # | Trigger | Call | Success | Failure handling |
|---|---|---|---|---|
| 1 | Register submit | `POST /auth/register` `{email,password}` | `201` → store token | `400` email taken (inline); `422` per-field |
| 2 | Login submit | `POST /auth/login` `{email,password}` | `200` → store token | `401` generic form error |
| 3 | App load / nav | `GET /workspaces` | `200 Workspace[]` | `401` → §6.2 |
| 4 | Create workspace | `POST /workspaces` `{name,description?,system_prompt?}` | `201` → navigate | `422` per-field |
| 5 | Workspace page | `GET /workspaces/{id}` | `200 Workspace` | `404` → not-found page |
| 6 | Update workspace | `PUT /workspaces/{id}` (changed fields only) | `200` → refetch | `422` per-field |
| 7 | Delete workspace | `DELETE /workspaces/{id}` | `204` → `/workspaces` | `404` → refetch + toast |
| 8 | Upload | `POST /workspaces/{id}/documents` multipart `file` | `201` → replace optimistic row, auto-train | `400` bad type (row-level); `404` workspace |
| 9 | Documents tab | `GET /workspaces/{id}/documents` | `200 WorkspaceDocument[]` | skeleton → error block |
| 10 | Train | `POST /workspaces/{id}/documents/{doc_id}/train` | `202` → start poll; `200` → already ready | `409` → let existing poll continue |
| 11 | Poll | `GET /workspaces/{id}/documents/{doc_id}/status` | `200` → update row; stop if terminal | `404` → stop + remove row |
| 12 | Delete document | `DELETE /workspaces/{id}/documents/{doc_id}` | `204` → remove row | `404` → refetch |
| 13 | Workspace chat | `POST /workspaces/{id}/chat` `{message,conversation_history?}` | `200` → answer + sources | `422` empty/oversize |
| 14 | Agents tab | `GET /workspaces/{id}/agents` | `200 Agent[]` | error block |
| 15 | Create agent | `POST /workspaces/{id}/agents` | `201` → navigate | `422` per-field |
| 16 | Agent page | `GET /workspaces/{id}/agents/{agent_id}` | `200 Agent` | `404` → not-found page |
| 17 | Update agent | `PUT .../agents/{agent_id}` (changed fields only) | `200` → refetch | `422` per-field |
| 18 | Delete agent | `DELETE .../agents/{agent_id}` | `204` → agents list | `404` → refetch |
| 19 | Test chat | `POST .../agents/{agent_id}/chat` `{message,conversation_id?}` | `200` → append, store id | `403` inactive; `429` slow down |
| 20 | New conversation | `POST .../agents/{agent_id}/conversations/new` | **`201`** → clear thread | — |
| 21 | Conversations tab | `GET .../conversations` | `200 Conversation[]` | error block |
| 22 | Thread view | `GET .../conversations/{conv_id}` | `200 {conversation,messages}` | `404` → not-found |
| 23 | Delete conversation | `DELETE .../conversations/{conv_id}` | `204` → back to list | `404` → refetch |
| 24 | Embed tab | `GET .../tokens` | `200 EmbedToken[]` (masked) | error block |
| 25 | Create token | `POST .../tokens` `{label,allowed_origins?}` | `201` → **one-time token modal** | `422` label |
| 26 | Token row | `GET .../tokens/{token_id}` | `200` masked | `404` → refetch |
| 27 | Edit / revoke | `PUT .../tokens/{token_id}` `{label?,allowed_origins?,is_active?}` | `200` → refetch | `422` per-field |
| 28 | Delete token | `DELETE .../tokens/{token_id}` | `204` → remove row | `404` → refetch |
| 29 | Snippet | `GET .../tokens/{token_id}/snippet` | `200 {snippet,token}` **full token** | `404` → inline not-found |
| 30 | Widget (customer site) | `GET /public/agent/{token}` | `200 PublicAgentInfo` | `401` invalid token; `403` revoked/agent inactive |
| 31 | Widget (customer site) | `POST /public/chat` `{token,message,conversation_id?}` | `200 {answer,sources,conversation_id}` | `401`/`403`/`422`/`429` — handled **inside `widget.js`, not the dashboard** |

### 6.10 CORS (what the dashboard must do)

The dashboard is **not** on `allow_origins=["*"]`. The backend restricts dashboard CORS to an
explicit allowlist configured via `ALLOWED_ORIGINS` in the backend `.env`:

```
http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://192.168.1.27:5173,http://192.168.1.27:3000
```

**Action required from the developer:** if your dev server runs on any other port (e.g.
`localhost:3001`, `127.0.0.1:4173`, a LAN IP that changed), add it to `ALLOWED_ORIGINS` in
`backend/.env` and restart the backend, or every dashboard request fails at the preflight with a
`400 Disallowed CORS origin` and a confusing `net::ERR_FAILED`.

Only `/public/*` (the widget endpoints) accepts **any** origin. That is deliberate: a widget runs on
arbitrary customer domains, and per-widget restriction happens in the application layer via a
token's `allowed_origins`.

The backend also sets `allow_credentials=True` and `allow_headers=["*"]` for the dashboard, and adds
`X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` to `/public/*` responses only.

---

## 7. Design System

### 7.1 Aesthetic

Modern, professional, **dark-primary** B2B SaaS. Reference: Linear, Vercel Dashboard, Supabase.
Dense but never cluttered; generous whitespace around controls; a calm dark canvas with one accent
colour used sparingly so it reads as "the important action". The product must feel trustworthy to a
business owner evaluating whether to paste a script into their revenue site. No playful gradients, no
excessive glassmorphism, no more than one shadow level visible at a time.

### 7.2 Colour palette

Semantic tokens first; raw hex only inside the token definitions.

**Brand / accent**

| Token | Hex | Use |
|---|---|---|
| `accent-500` | `#6366f1` | Primary buttons, active nav, links, focus ring, user bubbles |
| `accent-400` | `#818cf8` | Hover on accent surfaces |
| `accent-600` | `#4f46e5` | Active/pressed accent |
| `accent-300` | `#a5b4fc` | Accent text on dark backgrounds |
| `accent-500/12%` | `rgba(99,102,241,.12)` | Tinted backgrounds (dropzone hover, selected rows) |

**Surfaces (dark theme — the default)**

| Token | Hex | Use |
|---|---|---|
| `bg-canvas` | `#0b0d12` | Page background |
| `bg-surface` | `#12151c` | Cards, sidebar, table header |
| `bg-surface-raised` | `#181b23` | Modals, dropdowns, popovers |
| `bg-surface-hover` | `#1e222c` | Row/item hover |
| `bg-inset` | `#0e1116` | Inputs, code blocks, wells |
| `border-subtle` | `#22262f` | Default 1px borders |
| `border-strong` | `#2e3441` | Inputs, focused containers |
| `border-accent` | `#6366f1` | Focus ring, selected row indicator |

**Text**

| Token | Hex | Use |
|---|---|---|
| `text-primary` | `#e8eaf0` | Headings, primary body |
| `text-secondary` | `#9aa3b2` | Descriptions, table meta |
| `text-tertiary` | `#6b7280` | Placeholders, disabled |
| `text-inverse` | `#0b0d12` | Text on accent fills |

**Semantic**

| Token | Hex | Use |
|---|---|---|
| `success-500` | `#22c55e` | `ready`, active toggle on, success toasts |
| `success-400` | `#4ade80` | Success text on dark |
| `warning-500` | `#f59e0b` | `processing`, ungrounded answers, warning toasts |
| `danger-500` | `#ef4444` | `failed`, destructive buttons, error toasts |
| `danger-400` | `#f87171` | Danger text on dark |
| `info-500` | `#3b82f6` | Informational badges, in-progress copy |
| `neutral-500` | `#6b7280` | `uploaded` status, inactive states |

Light theme is optional and out of scope for v1. If added, do not re-derive hexes in components —
swap the token values only.

**Contrast:** body text on `bg-canvas` and `text-secondary` on surfaces must meet WCAG AA (4.5:1);
large text and icons 3:1. Verify `text-tertiary` is used only for non-essential decoration.

### 7.3 Typography

| Role | Family | Fallback |
|---|---|---|
| UI / body | **Inter** | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` |
| Numerals & code | **JetBrains Mono** | `ui-monospace, SFMono-Regular, Menlo, monospace` |

Self-host Inter (`woff2`, weights 400/500/600/700, `font-display: swap`). Self-hosting avoids a
third-party request on a low-bandwidth connection and removes a render-blocking round trip — this
matters for the target market. Load only the weights used.

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `text-2xl` | 24 / 32 | 600 | Page titles |
| `text-xl` | 20 / 28 | 600 | Section headings |
| `text-lg` | 16 / 24 | 600 | Card titles, agent names |
| `text-base` | 14 / 20 | 400 | Body, table cells |
| `text-sm` | 13 / 20 | 400 | Secondary text, table meta |
| `text-xs` | 12 / 16 | 500 | Badges, labels, helper text |
| `text-2xs` | 11 / 16 | 500 | Counters, overlines |

Weights in use: **400, 500, 600** only. Reserve 700 for marketing surfaces.

### 7.4 Spacing

Base unit **4px**. Scale: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64` (`space-1` … `space-16`).

| Context | Value |
|---|---|
| Card padding | `24px` (`space-6`) |
| Card gap between cards | `16px` (`space-4`) |
| Form field gap | `16px` |
| Label → input | `8px` (`space-2`) |
| Input → helper/error | `6px` |
| Table cell padding | `12px 16px` |
| Button padding | `10px 16px` (md), `8px 12px` (sm) |
| Section spacing | `32px` (`space-8`) |
| Page gutter | `24px` desktop, `16px` mobile |

### 7.5 Border radius

| Token | Value | Use |
|---|---|---|
| `radius-sm` | 6px | Badges, small chips, toggles |
| `radius-md` | 8px | Buttons, inputs, selects, table cells |
| `radius-lg` | 12px | Cards, dropdowns, popovers |
| `radius-xl` | 16px | Modals, code blocks |
| `radius-full` | 9999px | Pills, avatar, toggles, chat bubbles |

### 7.6 Shadows / elevation

| Level | Value | Use |
|---|---|---|
| `elevation-1` | `0 1px 2px rgba(0,0,0,.3)` | Cards at rest |
| `elevation-2` | `0 8px 24px rgba(0,0,0,.4)` | Modals, dropdowns, popovers |
| `elevation-3` | `0 16px 48px rgba(0,0,0,.5)` | Command palette, dialogs over modals |

On dark surfaces rely on `border-subtle` first and shadow second — a shadow alone is nearly invisible
on `#0b0d12`. The light-mode equivalents are out of scope.

### 7.7 Icons

**Phosphor Icons** (regular weight, 16/20/24px, `duotone` for empty states).

Justification vs the alternatives: Lucide is excellent but offers only two weights, so hierarchy in
dense tables and empty states is hard; Heroicons is outline-only at small sizes and reads thin on
dark surfaces; Phosphor provides six weights including `duotone` and `fill`, which lets one family
serve table density, navigation and marketing-grade empty states. Its tree-shaking is good, which
matters for the bandwidth constraint. Import via `@phosphor-icons/react` and load only the icons
actually used.

Rules: 16px in table rows and inputs, 20px in navigation, 24px on primary buttons and page headers.
Never mix icon families. Always pair a meaningful icon with a text label except in the table
overflow menu.

### 7.8 Document status badges

Exactly four statuses exist and the API will never send anything else. Do not add states.

| `status` | Colour | Badge | Animation | Copy |
|---|---|---|---|---|
| `uploaded` | `neutral-500` grey | Grey dot, outline | none | "Uploaded" |
| `processing` | `warning-500` amber | Amber dot, tinted bg | **pulsing dot** + looping indeterminate bar | "Training…" |
| `ready` | `success-500` green | Green dot, solid | none | "Ready" |
| `failed` | `danger-500` red | Red dot, solid | none | "Failed" |

- `processing` is the only animated state, and it must respect
  `prefers-reduced-motion: reduce` (swap the pulse for a static dot, keep the looping bar or
  replace it with plain "Training…").
- Always show `chunk_count` beside a `ready` badge ("Ready · 412 chunks"). Show `0 chunks` on
  `ready` too — it means the document produced nothing searchable and is a support signal.
- `failed` badges must include a Retry affordance.

### 7.9 Agent and token active toggles

| State | Visual |
|---|---|
| Active | Track `success-500`, knob right, white knob; a green dot + the word **"Active"** next to it |
| Inactive | Track `neutral-500` at 40% opacity, knob left; grey dot + the word **"Inactive"** |

Rules: the state is **never** communicated by colour alone — pair the colour with a dot **and** a
text label, and set `aria-checked`. The `Agent.is_active` field arrives as `0 | 1` while
`EmbedToken.is_active` arrives as a real boolean, so normalise with
`Boolean(agent.is_active)` before rendering. An inactive agent's widget returns `403` — say so in
the UI next to the toggle: *"Turning this off makes the live widget stop responding immediately."*
---

## 8. Responsive Behaviour

| Breakpoint | Width | Layout |
|---|---|---|
| Desktop | ≥ 1280px | Fixed 256px sidebar + fluid main area (max-width 1400px content) |
| Tablet | 768–1279px | Collapsible 64px icon rail; hover tooltips; tables drop secondary columns |
| Mobile | < 768px | Sidebar becomes an overlay drawer via hamburger; tables become stacked cards |

**Desktop (≥ 1280px)** — the design target. Persistent 256px sidebar with workspace switcher; content
area with a sticky top bar; multi-column card grids (agents: 3-up, workspaces: 2–3-up); tables show
all columns.

**Tablet (768–1279px)** — sidebar auto-collapses to a 64px icon rail with tooltips on hover; grids drop
to 2-up; documents table hides `size_bytes` and `created_at`; agent detail tabs stay horizontal but
scroll if they overflow.

**Mobile (< 768px)** — top bar gains a hamburger opening the sidebar as a left drawer (80vw max,
overlay scrim, closes on navigation). Grids become 1-up. **Every `DataTable` renders as stacked
cards**: each row becomes a bordered block with the column labels as `text-xs` captions and the
primary value (`filename`, `title`, `label`) as the card heading. Agent detail tabs become a
horizontally scrollable segmented control. Modals go full-screen (`radius-0`, 100dvh) with a sticky
footer. The code block gets `wrap: true` on small screens.

**Mobile-critical pages** (must be fully usable on a phone — these are often completed on a phone in
Tanzania):

1. `/login` and `/register` — highest priority; single column, 44px minimum touch targets, no
   horizontal scroll at 320px.
2. **The embed snippet page** (`?tab=embed&snippet=…`) — the merchant is often on site on a phone and
   needs to copy the snippet. Code block wraps, copy button is ≥ 44px, the step checklist is
   readable.
3. **Document upload + training status** — merchants photograph/scan documents on a phone. The dropzone
   must have a large "Choose file" tap target, and `processing` status must be legible.
4. **Agent chat preview** — usable read-only; the composer sticks above the mobile keyboard.

**Acceptable to degrade on mobile:** the dashboard overview (stats grid), workspace settings, and
conversation thread view may show a "best on a larger screen" banner while remaining fully
scrollable and readable. Do not hide functionality — degrade layout only.

Performance rule for the target market: target **LCP < 2.5s on a 3G/4G connection**. Self-host fonts,
code-split the dashboard routes, lazy-load heavy tables, and keep the initial JS bundle under
~150 KB gzipped (see [§10](#10-frontend-tech-stack-recommendation)).

---

## 9. Key UX Decisions (Explicit Rules)

These are **mandatory**. They are written as rules because each one exists because the API forces it.

### 9.1 Training status polling

1. Poll `GET /workspaces/{wsId}/documents/{docId}/status` **every 3000 ms**.
2. Start polling only on a `202` from `train`, or on page load for a document whose status is
   `uploaded` or `processing`.
3. **Stop when `status` is `ready` or `failed`.** Nothing else ends the loop.
4. Never stop on a network error or `5xx` — retry on the next tick.
5. A `200` from `train` means "already ready": set the badge directly, **do not poll**.
6. A `409` from `train` means a run is already in flight: do not start a second poller, do not toast.
7. Stop on `404`, on unmount, on workspace switch, and after a 10-minute cap (show "Taking longer than
   expected").
8. Exactly one "Training complete" toast per document, emitted by list state — not by each observer.
9. The progress indicator is **indeterminate**. Never render a fake percentage; the API never returns
   progress.

### 9.2 JWT expiry mid-session

1. Hold the token **in memory only**. No `localStorage`, no `sessionStorage`, no cookie.
2. On **any** `401`: clear the token, toast "Your session expired. Please sign in again." (4 s,
   `warning`), then `router.replace('/login?redirect=<current path>')`.
3. **Deduplicate** concurrent 401s with a module-level flag so the user sees one toast, not ten.
4. Preserve the user's location in `?redirect=` and honour it after login; default `/dashboard`.
5. Never render a protected page before the auth check resolves (no flash of protected content).
6. There is no refresh token and the JWT has no `iat`, so **do not** display a "session expires in
   6 days" countdown — you cannot compute it reliably. If you must show anything, decode `exp` and
   label it "Signed in until …", tolerating an undecodable token.

### 9.3 The full token is shown once — mandatory UI treatment

1. The full token arrives **only** in the `201` response of `POST .../tokens` and in
   `GET .../tokens/{id}/snippet`. Treat it as write-once, read-immediately.
2. On `201`, open a modal **immediately**. Never route away, never put it in a toast.
3. The modal must contain, in order:
   - A `warning` `AlertBanner`: *"Copy this token now. We only show it once — if you lose it, delete
     this token and create a new one. We cannot recover it."*
   - The **embed snippet** with a **Copy snippet** button (primary action — it already contains the
     token).
   - The raw token in a monospace block with a **Copy token** button.
   - A 3-step checklist: copy → paste before `</body>` → verify live.
   - A primary button "I've copied it".
4. **Guard dismissal:** if closed via overlay or `Esc` without a copy, re-open once with a stronger
   warning. Track `copied` in component state.
5. Keep the value in component state only. Null it on close. Never put it in a URL, global store,
   `localStorage`, console logs, analytics, or an error reporter.
6. Elsewhere the UI shows only the masked value from the API (`a3f7c91b…`). To reveal the full token
   again, call `GET .../tokens/{id}/snippet` on demand.

### 9.4 Mandatory confirmation dialogs

Every destructive or service-affecting action **must** be confirmed. Copy is mandated:

| Action | Dialog title | Body | Confirm button |
|---|---|---|---|
| Delete document | "Delete document?" | "This removes **{filename}** and everything extracted from it. The agent will no longer be able to answer questions using this document. This cannot be undone." | "Delete document" (danger) |
| Delete agent | "Delete agent?" | "This permanently deletes **{name}**, all of its conversations, and all of its embed tokens. Any website still using those tokens will stop working immediately. This cannot be undone." | "Delete agent" (danger) |
| Delete workspace | "Delete workspace?" | "This permanently deletes **{name}** — every document, chunk and embedding, all agents, all conversations and all embed tokens. This cannot be undone." | "Delete workspace" (danger) |
| Delete token | "Delete embed token?" | "The widget on **{label}** will stop working immediately. If you only want to pause it, revoke it instead — that can be undone." | "Delete token" (danger) |
| Revoke token | "Revoke embed token?" | "The widget on **{label}** will stop responding immediately, for every visitor. You can re-activate it later." | "Revoke token" (danger) |
| Delete conversation | "Delete conversation?" | "This permanently deletes this conversation with **{agent}**." | "Delete conversation" (danger) |

Rules: the confirm button is never the default focus (focus the cancel button); Esc and overlay click
cancel; the confirm button shows a spinner while the request is in flight and must not double-fire;
never show a confirmation for non-destructive actions.

### 9.5 Toast duration and placement

| Variant | Duration | Placement |
|---|---|---|
| `success` | 3000 ms | Bottom-right (desktop) / top-centre (mobile), stacked, newest at the bottom |
| `info` | 4000 ms | Same |
| `warning` | 4000 ms | Same |
| `error` | 6000 ms | Same |
| `error` with an action | 8000 ms (action button: "Retry") | Same |

Rules: max 4 visible — the oldest is dismissed to make room. Toasts never carry the only copy of
information (that is what modals are for). Field validation is **never** a toast. Do not toast on
successful autosave — use an inline "Saved" tick. Copy-to-clipboard feedback is a **button state
change**, not a toast.

### 9.6 Empty state copy (mandated)

| Section | Title | Description | Action |
|---|---|---|---|
| Workspaces | "No workspaces yet" | "A workspace holds your documents and the agents built from them. Start with one." | "Create workspace" |
| Documents | "No documents yet" | "Upload your first document to give your agents something to answer from. PDF, TXT or DOCX." | "Upload document" |
| Documents — agent gate | "Train a document first" | "An agent with no knowledge base can't answer questions. Train at least one document, then come back." | "Go to Documents" |
| Agents | "No agents yet" | "An agent is your AI assistant — a name, a personality and the knowledge it answers from." | "New agent" |
| Conversations | "No conversations yet" | "Once your widget is live, visitor conversations appear here." | "Start a conversation" |
| Embed tokens | "No embed tokens yet" | "An embed token is the key that lets your website talk to this agent. Create one to get your embed code." | "Create embed token" |
| Search results | "No matches" | "Nothing matched **{query}**." | "Clear search" |
| Dashboard | "Welcome to XvecBot" | "Three steps to your first live chat widget." | "Create your first workspace" |

### 9.7 Disabled states for unmet prerequisites

| Control | Disabled when | Presentation |
|---|---|---|
| **New agent** | Workspace has **0 documents with `status === "ready"`** | Disabled + tooltip *"Train at least one document first"*; the Documents empty state links here. `uploaded`/`processing`/`failed` do **not** count. |
| **New embed token** | Agent is `is_active === 0` | Disabled + tooltip *"Activate the agent before creating a token"* |
| **Copy snippet** | Token id unknown | Disabled until the snippet call resolves |
| **Test tab composer** | Agent is inactive | Input disabled + inline banner "This agent is inactive. Activate it to test." |
| **Upload** | Workspace deleted / 404 | Section replaced by the not-found state |
| **Edit config fields** | Save in flight | Fieldset disabled, button in `loading` |

Never disable a control without an explanation adjacent to it. A greyed button with no reason is a
support ticket.

### 9.8 Dashboard preview vs the public widget — different UIs

These are **not** the same component. Do not reuse the widget in the dashboard, and do not reuse the
dashboard chat in the widget.

| | Dashboard Test tab | Public widget (`widget.js`) |
|---|---|---|
| Container | Docked panel inside the page grid | Fixed floating bubble + panel, Shadow DOM |
| Served by | The dashboard app (React) | Static `widget.js` from the platform |
| Conversation state | React state; can be reset | `sessionStorage` key `xvecbot_conv_{token}` |
| Welcome message | Rendered as the first bubble on open | Same, once per session |
| Shows `model_used` | **Yes** — small caption | **No** — never exposed publicly |
| Shows token/request metadata | Yes (embed tab) | No |
| Unread badge | No | Yes, when a reply lands while closed |
| Keyboard | Enter sends, Shift+Enter newline, Esc closes | Same |
| Styling | Design-system tokens | Inline CSS scoped in a shadow root, primary colour from `data-color` |

Only the message-bubble *shape* is shared conceptually. They are separate implementations.

### 9.9 Conversation history ordering and titles

1. Order by `updated_at` **descending** — most recent first. Do not offer a sort control; there is no
   server-side sort and one ordering is correct.
2. Show `title` as the primary label. It is `"New Conversation"` until the backend auto-titles it
   from the **first user message** — so the title legitimately changes after turn 1. Do not treat this
   as a bug and do not block on it.
3. Render `updated_at` as relative time ("2 hours ago") with the absolute timestamp in a `title`
   tooltip.
4. There is **no pagination**. Render the whole array. If a list ever exceeds a few hundred rows,
   virtualise the list client-side — never render a paginator.
5. The thread view is **read-only**. Banner: *"This is a preview of a stored conversation. To continue
   chatting, open the Test tab."*

### 9.10 Pagination — there isn't any

No list endpoint accepts `page`, `limit`, `offset`, `cursor`, `sort` or `order`, and none return a
total count (the legacy `/api/v1/documents/` `DocumentList` shape does, but that route is API-key
authenticated and not part of the dashboard). Consequences:

1. **Never render a paginator.** It cannot work.
2. Client-side search/filter is expected and fine (workspaces, conversations, tokens).
3. If a list could grow large, virtualise rows client-side.
4. If the backend later adds pagination, the `DataTable` must be refactored before shipping a
   paginator — flag this to the backend team as a known future change.

### 9.11 Field-update semantics (surprising, must be handled)

`PUT /workspaces/{ws}/agents/{agent_id}` **ignores `null` values**. Consequences:

1. Always send only the fields that actually changed (`model_dump(exclude_unset=True)` semantics).
2. A field cannot be reset to `null` through `PUT`. Workarounds that *do* work:
   - `allowed_origins` → send `[]`; the backend stores `null` (meaning "any origin").
   - `welcome_message` → send `" "`; the public API treats blank as "use the default greeting".
3. Surface this in the UI as helper text so users do not think clearing is broken:
   *"Clear the field and save to reset it to the platform default."*
4. Never send a `null` and assume it saved. If the UI shows a field as empty after save, refetch.

### 9.12 Miscellaneous mandatory rules

1. **Never render `dangerouslySetInnerHTML`.** LLM answers and document filenames are untrusted text.
   Render as text with `white-space: pre-wrap`.
2. **`sources: []` is not an error.** It means retrieval found nothing. Show the amber grounding
   warning; never an error state.
3. **Optimistic updates are allowed** for token revoke and document delete; roll back on failure.
4. **`PUT .../agents/{id}` cannot change `workspace_id`** — it is not in the request schema.
5. **Origin values are bare hostnames.** Normalise user input by stripping scheme, trailing slash and
   path before sending. Matching is exact, so `mystore.co.tz` and `www.mystore.co.tz` must both be
   listed to cover both. Always show this as helper text.
6. **Rate limiting exists only on `/public/chat`** (20 requests per minute per embed token). It does
   not affect the dashboard, but the Test tab consumes the agent's own pipeline — do not add client
   rate limiting there.
7. **Timestamps are naive ISO strings** without a `Z`/offset suffix (they are UTC server time). Format
   them as UTC. A single naive local-time parse will show wrong times.
8. **File size** — format `size_bytes` as KB/MB with one decimal. The workspace upload route enforces
   **no server-side cap**; warn above 50 MB client-side.

---

## 10. Frontend Tech Stack Recommendation

Constraints that drive these choices: African market, **bundle size matters**, **CDN egress costs
money**, **low-bandwidth and intermittent connectivity must degrade gracefully**, and the team is
small. Priorities in order: bundle size, resilience, developer velocity, SEO irrelevance (this is a
behind-login app — SEO is worth nothing).

| Layer | Choice | Justification |
|---|---|---|
| **Framework** | **Next.js 15 (App Router) + React 19, TypeScript `strict`** | Single deployable (Node server) — no second hosting bill or Caddy/Nginx tier. App Router gives nested layouts (the persistent sidebar) and per-route code splitting for free, which is what keeps the initial bundle small. Static export was rejected: the auth model is in-memory tokens ([§6.2](#62-jwt-storage-and-the-401-flow)), which needs no server but also gets no benefit from SSR; a plain SPA would be lighter, but App Router's streaming + `loading.tsx` skeletons make the perceived performance far better on slow connections. Choose **Vercel** (zero-config, generous free tier, global CDN) or a single cheap VPS with `pm2` if data residency in Tanzania/EAR is required. |
| **Styling** | **Tailwind CSS v4** | Utility classes mean near-zero runtime CSS-in-JS cost (the main argument against `styled-components`, which is a real per-render and bundle cost here). Ships only the utilities used. Design tokens are declared once in `@theme` and consumed by both the app and any inline widget-preview component. No separate CSS build step, no naming debates. |
| **State — server** | **TanStack Query v5** | The app is ~85% server state. Gives caching, background refetch, `keepPreviousData` for tab switching, and — critically — the mutation lifecycle we need for the "one-time token" modal and optimistic revoke/delete. Hand-rolled `useEffect` fetching would be more bytes and more bugs. Configure a long `staleTime` (60s) to reduce requests on a flaky link. |
| **State — client** | **Zustand** | ~1 KB. Holds session (`token`, `user`), the active workspace id, and the one-time token. Rejected: Redux Toolkit (too much boilerplate for this size), Context alone (causes re-render storms and is awkward for cross-route session state). |
| **Data fetching (HTTP)** | **`fetch` wrapper** (`lib/api-client.ts`, [§6.3](#63-attaching-the-token)) | A 30-line wrapper beats `axios` here: the browser `fetch` is native and zero-cost, the wrapper centralises the 401 rule and error normalisation, and dropping a ~13 KB dependency matters on a metered connection. Do **not** use OpenAPI codegen — hand-written types ([§6.8](#68-typescript-types-copy-these)) are smaller and the API is small. |
| **Forms** | **React Hook Form + Zod** | RHF keeps field state out of the render path (smaller, faster forms); Zod gives one schema per form used for validation, for parsing API responses, and for deriving defaults — so client and server validation can never drift. `zodResolver` wires them together. Total ~13 KB gzipped, worth it. |
| **Routing** | **Next.js App Router** (`app/`) | Free code splitting and nested layouts. No `react-router` needed. |
| **UI primitives** | **Radix UI primitives + hand-rolled components** | Radix gives accessible, unstyled behaviour (focus trap, `aria`, keyboard, popover positioning) at ~1–3 KB per primitive and **no visual opinion**, so the design system in [§7](#7-design-system) is honoured exactly. Rejected: shadcn/ui as a dependency (copy the source in — it *is* Radix + Tailwind, and copying gives ownership with no runtime cost), Chakra/MUI/Ant (heavily opinionated; fighting them costs more than it saves). |
| **Tables** | **TanStack Table v8** (headless) + a hand-rolled shell | Sorting/selection logic without opinionated markup. Needed because of the responsive stacked-card requirement ([§8](#8-responsive-behaviour)). |
| **Toasts** | **Sonner** | ~3 KB, sensible defaults, stacked, promise-friendly, and it can be themed to the design tokens. Hand-rolling toasts (positioning, timers, stacking, a11y) is a bad use of time. |
| **Icons** | **Phosphor** via `@phosphor-icons/react`, imported per-icon | See [§7.7](#77-icons). Never the `*` barrel import. |
| **Code highlighting** | **`shiki` at build time** (via `rehype-pretty-code` on a static MD route, or a small build step) | The snippet is 6 lines of HTML. Runtime highlighters (`highlight.js`, `prismjs`) ship 10–100 KB+ for nothing. Shiki produces output at build time (zero runtime JS, real TextMate grammars, themeable to our tokens) and can be limited to `html` only. If even that is too much, render the snippet in a `<pre>` with two spans (tag vs attribute) — perfectly acceptable for 6 lines. |
| **Markdown rendering** | **None by default.** LLM answers are plain text | An `allowlist` markdown renderer (`react-markdown`) is a reasonable later addition, but render as text by default ([§9.12](#912-miscellaneous-mandatory-rules)). Do not ship a markdown parser until a real need appears. |
| **Testing** | **Vitest + React Testing Library** (unit), **Playwright** (3 E2E smoke paths) | Playwright's E2E covers register → workspace → document → agent → token → snippet. |
| **Utilities** | **Tailwind + `clsx`** + `tailwind-merge` | Tiny; variant conflict resolution. Skip `class-variance-authority`. |

**Bundle budget (enforce in CI):** initial JS ≤ **150 KB gzip**, any single route chunk ≤ **80 KB
gzip**, CSS ≤ **30 KB gzip**. Fonts self-hosted `woff2`, `font-display: swap`, `preload` the 400 and
600 weights only. Reject: any runtime charting library (not needed), any i18n framework (5 fixed
languages → a small dictionary file), any carousel/animation library (use CSS).

---

## 11. Folder Structure

```
frontend/
├── public/
│   ├── favicon.svg
│   └── og-image.png
├── src/
│   ├── app/
│   │   ├── layout.tsx                      # root layout: fonts, providers, toast viewport
│   │   ├── globals.css                     # Tailwind v4 @import + @theme design tokens
│   │   ├── (auth)/
│   │   │   ├── layout.tsx                  # centred AuthShell, no sidebar
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (app)/
│   │   │   ├── layout.tsx                  # Sidebar + TopBar + auth guard
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── workspaces/
│   │   │   │   ├── page.tsx                # list
│   │   │   │   ├── new/page.tsx
│   │   │   │   └── [wsId]/
│   │   │   │       ├── layout.tsx          # PageHeader + tab nav (?tab=)
│   │   │   │       ├── page.tsx            # Documents tab (default)
│   │   │   │       ├── agents/
│   │   │   │       │   ├── page.tsx        # Agents grid
│   │   │   │       │   ├── new/page.tsx
│   │   │   │       │   └── [agentId]/
│   │   │   │       │       ├── layout.tsx  # Agent header + tabs
│   │   │   │       │       ├── page.tsx    # Overview
│   │   │   │       │       ├── conversations/
│   │   │   │       │       │   └── [convId]/page.tsx
│   │   │   │       │       └── loading.tsx
│   │   │   │       └── error.tsx
│   │   │   │       ├── loading.tsx
│   │   │   │       └── error.tsx
│   │   │   └── account/page.tsx
│   │   ├── api/                            # route handlers (only for the snippet preview)
│   │   ├── error.tsx                       # global error boundary
│   │   ├── not-found.tsx
│   │   └── loading.tsx
│   ├── components/
│   │   ├── ui/                             # design-system primitives (Radix-based)
│   │   │   ├── button.tsx
│   │   │   ├── input.tsx
│   │   │   ├── textarea.tsx
│   │   │   ├── select.tsx
│   │   │   ├── range-slider.tsx
│   │   │   ├── origin-chip-input.tsx
│   │   │   ├── modal.tsx
│   │   │   ├── confirmation-dialog.tsx
│   │   │   ├── alert-banner.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── toggle.tsx
│   │   │   ├── skeleton.tsx
│   │   │   ├── data-table.tsx
│   │   │   ├── definition-list.tsx
│   │   │   ├── empty-state.tsx
│   │   │   ├── relative-time.tsx
│   │   │   ├── stat-card.tsx
│   │   │   ├── code-snippet.tsx
│   │   │   └── copy-button.tsx
│   │   ├── layout/
│   │   │   ├── app-shell.tsx
│   │   │   ├── sidebar-nav.tsx
│   │   │   ├── top-bar.tsx
│   │   │   ├── breadcrumb.tsx
│   │   │   ├── auth-shell.tsx
│   │   │   └── workspace-switcher.tsx
│   │   ├── chat/
│   │   │   ├── chat-panel.tsx
│   │   │   ├── chat-message-bubble.tsx
│   │   │   ├── chat-input.tsx
│   │   │   ├── typing-indicator.tsx
│   │   │   ├── source-chips.tsx
│   │   │   └── grounding-warning.tsx
│   │   ├── documents/
│   │   │   ├── file-upload-zone.tsx
│   │   │   ├── document-table.tsx
│   │   │   ├── training-status-indicator.tsx
│   │   │   └── document-row.tsx
│   │   ├── agents/
│   │   │   ├── agent-card.tsx
│   │   │   ├── agent-form.tsx
│   │   │   ├── model-select.tsx
│   │   │   ├── temperature-slider.tsx
│   │   │   └── language-select.tsx
│   │   ├── embed/
│   │   │   ├── token-table.tsx
│   │   │   ├── token-form-modal.tsx
│   │   │   ├── one-time-token-modal.tsx
│   │   │   └── snippet-checklist.tsx
│   │   └── common/
│   │       ├── page-header.tsx
│   │       ├── tab-nav.tsx
│   │       ├── error-panel.tsx
│   │       ├── not-found-panel.tsx
│   │       └── confirm-gate.tsx
│   ├── hooks/
│   │   ├── use-auth.ts
│   │   ├── use-training-poll.ts          # the 3 s poll loop (§6.4)
│   │   ├── use-agents.ts
│   │   ├── use-documents.ts
│   │   ├── use-conversations.ts
│   │   └── use-embed-tokens.ts
│   ├── lib/
│   │   ├── api-client.ts                 # fetch wrapper + 401 rule (§6.3)
│   │   ├── api-error.ts                  # error normalisation (§6.1)
│   │   ├── auth.ts                       # in-memory session (§6.2)
│   │   ├── constants.ts                  # route limits, MAX_MESSAGE_LENGTH, POLL_MS
│   │   ├── reference-data.ts             # MODELS, LANGUAGES (§6.7)
│   │   ├── format.ts                     # bytes, relative time (UTC-safe)
│   │   └── cn.ts
│   ├── schemas/                          # Zod — shared by forms and API parsing
│   │   ├── auth.ts
│   │   ├── workspace.ts
│   │   ├── document.ts
│   │   ├── agent.ts
│   │   ├── token.ts
│   │   └── chat.ts
│   ├── stores/
│   │   └── session.ts                    # Zustand: token, user, activeWorkspaceId
│   └── types/
│       └── api.ts                        # the interfaces from §6.8
├── e2e/
│   ├── auth.spec.ts
│   ├── knowledge.spec.ts                 # workspace → upload → train
│   └── agent-to-widget.spec.ts           # agent → token → snippet
├── .env.local                            # NEXT_PUBLIC_* (§12)
├── next.config.ts
├── tailwind.config.ts / app/globals.css
├── package.json
├── tsconfig.json
└── README.md
```

---

## 12. Environment Variables

```bash
# frontend/.env.local
# Base URL of the backend. No trailing slash.
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Product name shown in the sidebar, page titles and the login brand panel.
NEXT_PUBLIC_APP_NAME=XvecBot

# Public origin of this dashboard (used for absolute links and OG tags).
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

| Variable | Required | Dev value | Production value | Notes |
|---|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | **yes** | `http://localhost:8000` | `https://api.xvecbot.tz` | No trailing slash. Must be reachable from the browser, so it is the **public** backend URL, not an internal one. |
| `NEXT_PUBLIC_APP_NAME` | no | `XvecBot` | `XvecBot` | Sidebar wordmark, `<title>`, auth panel. |
| `NEXT_PUBLIC_SITE_URL` | no | `http://localhost:3000` | `https://app.xvecbot.tz` | Canonical URL, OG tags. |

**Rules**

1. Only variables prefixed `NEXT_PUBLIC_` reach the browser. **Never** put the OpenRouter key, the
   JWT secret, or any backend secret in a `NEXT_PUBLIC_*` variable — they are compiled into the
   client bundle and are publicly readable.
2. The dashboard holds **no** embed token in env; tokens are fetched per request with the JWT.
3. Validate `NEXT_PUBLIC_API_BASE_URL` at boot and render a clear configuration-error screen if it is
   missing, instead of failing with a confusing network error on every page.
4. If the dev server runs on a port not in the backend's `ALLOWED_ORIGINS` (currently 5173 and 3000
   only), add it there — see [§6.10](#610-cors-what-the-dashboard-must-do).
5. There is **no** `NEXT_PUBLIC_WIDGET_URL` variable. The widget URL shown in the snippet comes from
   the backend's `APP_PUBLIC_URL` setting, returned inside the snippet itself. Do not hardcode or
   reconstruct it in the frontend.

---

## 13. Handoff Notes for the Designer

### 13.1 Figma file structure

```
📁 XvecBot Dashboard
├── 📄 00 — Foundations        (design tokens, type scale, colour, spacing, icons)
├── 📄 01 — Components         (the component library frame, §13.2)
├── 📄 02 — Screens            (every screen, §13.3)
├── 📄 03 — Flows              (clickthrough prototypes, §13.4)
├── 📄 04 — Responsive         (tablet + mobile variants)
└── 📄 05 — Archive
```

Set Figma variables from the tokens in [§7](#7-design-system): colour (`accent-500`, `bg-canvas`,
`bg-surface`, `bg-surface-raised`, `bg-inset`, `border-subtle`, `border-strong`, `text-primary`,
`text-secondary`, `text-tertiary`, `success-500`, `warning-500`, `danger-500`, `info-500`,
`neutral-500`), spacing (4/8/12/16/20/24/32/40/48/64), radius (6/8/12/16/9999), and the 7-step type
scale. Use Figma **Variables + Modes** if your team prefers; do not hardcode hexes in components.

### 13.2 Components frame — build these as Figma components with variants

Button (5 variants × 3 sizes × 4 states) · Input (default/focus/error/disabled) · Textarea (with
counter variant) · Select · RangeSlider · OriginChipInput · Modal (3 sizes) · ConfirmationDialog
(2 variants) · AlertBanner (4 tones) · Badge (6 tones × with/without dot × animated) · Toggle
(on/off/disabled/loading) · Skeleton (6 variants) · DataTable (desktop + stacked-card mobile) ·
DefinitionList · EmptyStateBlock (5 mandated copy variants) · StatCard · CodeSnippetDisplay (with
copy state) · RelativeTime · SidebarNav (expanded/collapsed/mobile-drawer) · TopBar · Breadcrumb (2 /
4 / truncated) · ChatMessageBubble (user / assistant / assistant-ungrounded / error / pending) ·
ChatInput (idle / with text / disabled) · SourceChips · TypingIndicator · AgentCard
(active/inactive) · WorkspaceCard · FileUploadZone (idle/drag-over/uploading/error) ·
TrainingStatusIndicator (4 statuses) · CopyButton (idle/copied).

### 13.3 Screens frame — every artboard to produce

Desktop (1440×1024) unless noted:

1. Login · 2. Register · 3. Dashboard — populated · 4. Dashboard — empty/onboarding ·
5. Workspaces list · 6. Workspaces empty · 7. Create workspace · 8. Workspace → Documents (empty) ·
9. Workspace → Documents (uploading) · 10. Workspace → Documents (ready) · 11. Workspace → Documents
(mixed statuses, incl. failed) · 12. Workspace → Agents (empty + gated) · 13. Workspace → Agents
(populated) · 14. Create agent · 15. Agent → Overview · 16. Agent → Test (with messages) ·
17. Agent → Test (empty + suggested questions) · 18. Agent → Conversations list ·
19. Conversation thread · 20. Agent → Embed tokens (empty) · 21. Agent → Embed tokens (populated) ·
22. **One-time token modal** · 23. Create/edit token modal · 24. Snippet view ·
25. Snippet view — mobile (375×812) · 26. Workspace → Settings · 27. Delete confirmation dialogs (3) ·
28. Account · 29. 404 (resource not found) · 30. Error panel / network failure ·
31. Loading skeletons (all patterns) · 32. Empty search results

Mobile (375×812) mandatory variants: Login, Register, Documents + training status, Snippet view.

### 13.4 Flows needing a clickthrough prototype

1. **Onboarding** — empty dashboard → create workspace → upload → train (processing → ready) →
   create agent → copy snippet.
2. **Knowledge** — drop file → optimistic row → `processing` badge animating → `ready` with chunk
   count. Include the `failed` → Retry branch.
3. **Agent configuration** — create form → validation error → success → Overview.
4. **Agent test** — open panel → welcome bubble → send → typing → answer + citation chips →
   follow-up (same conversation).
5. **Token one-time reveal** — create → warning modal → copy → checklist complete → paste steps.
   **This flow must get the most design attention** — it is the moment of highest anxiety in the
   product (fear of losing a credential).
6. **Revoke** — toggle off → confirmation → live widget stops.
7. **Delete cascade** — delete agent dialog showing all consequences.

### 13.5 Design tokens to define

Colour (14 semantic + 5 accent = 19), typography (Inter 400/500/600 + JetBrains Mono 400, 7-step scale),
spacing (10 steps), radius (5), elevation (3), icon sizes (16/20/24). Name them exactly as in
[§7](#7-design-system) so the Tailwind `@theme` and the Figma variables stay in sync.

### 13.6 What you must NOT change

1. **Document status is one of exactly four values**: `uploaded`, `processing`, `ready`, `failed`. No
   fifth state, no custom labels beyond the copy in [§7.8](#78-document-status-badges).
2. **Embed token masking is fixed**: `first 8 characters + "..."` (11 chars total). Do not design a
   different mask, a partial reveal, or a "show token" toggle in the table.
3. **`allowed_origins` is `null` or an array** — exactly two states: "Any origin" or a list. There is
   no wildcard-checkbox + text-field hybrid.
4. **The full token appears exactly once**, in a modal, with a warning. Do not design the token list
   with a reveal button, and do not show the full value in a table row or a toast.
5. **The snippet is one script tag**; the widget takes `data-agent`, `data-position` (`right`/`left`),
   `data-color`, `data-lang`. Do not design a config panel implying more widget options exist.
6. **Conversation title is generated by the backend** and starts as `"New Conversation"`. Do not
   design a rename-title control or an editable title.
7. **Conversation thread view is read-only.** No input box, no send button, no regenerate action.
8. **No pagination controls anywhere** ([§9.10](#910-pagination--there-isnt-any)). No "Load more",
   no page numbers, no rows-per-page selector.
9. **No sort controls on conversation history** — ordering is fixed, most recent first.
10. **Do not design a document rename feature** — the API has no endpoint for it.
11. **Do not design an agent "clone/duplicate" action** — no endpoint exists.
12. **Model list is fixed at 6 options** ([§6.7](#67-model-dropdown-reference-data)) with only two
    groups (Paid / Free). Do not add a "custom model" text field: unknown ids are silently coerced to
    the default server-side, so a custom field would silently mislead users.
13. **Temperature range is 0.0–1.0.** Do not extend to 2.0.
14. **Do not design a global "Assistant personality" marketplace or template gallery** — no endpoint.

### 13.7 Accessibility baseline (WCAG 2.1 AA minimum)

- All interactive elements reachable and operable by keyboard; visible `focus-visible` ring (2px
  `accent-500` + 2px offset). Never `outline: none` without a replacement.
- Status is never colour-only. The `processing` badge needs an animated **and** textual indicator;
  toggles need a dot **and** a word; validation errors need an icon **and** text.
- Contrast ≥ 4.5:1 for body text, ≥ 3:1 for large text and UI boundaries. Verify `text-tertiary`
  (`#6b7280`) on `bg-surface` (`#12151c`) — it is close to the limit; use it for decoration only.
- `aria-live="polite"` on the chat log; `role="alert"` on error toasts; `aria-busy` on loading
  containers; `aria-current="page"` on the active breadcrumb.
- Modals: focus trap, `Esc` to close, focus restored to the trigger, and the confirm button is **not**
  autofocused.
- Forms: every input has a real `<label>` (not a placeholder as the label); errors are linked via
  `aria-describedby`; `aria-invalid` on failure.
- Respect `prefers-reduced-motion: reduce` — the `processing` pulse and all skeleton shimmer must
  degrade to a static state.
- Minimum touch target 44×44 px on mobile.
- Images/illustrations need meaningful alt text; decorative icons `aria-hidden`.
- Chat messages must be readable by a screen reader in order: use a `<ol>`/log region with
  `aria-live="polite"`, and label each bubble with its author and timestamp.

---

## 14. Handoff Notes for the Developer

### 14.1 Run the backend locally

```bash
# from the repo root
cd /home/jteckz7/Xvec-chat/backend

# create + activate the venv once (Python 3.13)
../.venv/bin/python -m venv ../.venv      # skip if it already exists

# start the API on :8000
../.venv/bin/uvicorn app.main:app --port 8000
# ...or with autoreload while developing the backend:
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

First start takes **~30–160 s** because it loads the sentence-transformers embedding model. It is not
hung — wait for `Application startup complete`. Interactive API docs: **http://localhost:8000/docs**.

### 14.2 API base URL for development

```
http://localhost:8000
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`. The backend must be
reachable **from your browser**, so if you access the dashboard via a LAN IP (e.g.
`http://192.168.1.5:3000`), still point at the backend's LAN-reachable address — and add that
dashboard origin to the backend's `ALLOWED_ORIGINS`, or you will get a CORS failure
([§6.10](#610-cors-what-the-dashboard-must-do)).

### 14.3 Known Phase 1 issue — do not build a UI for it

`POST /api/v1/query` is **broken**: it fails with `'citations' is already being used as a state key`
(LangGraph state-key collision in the Phase 1 graph) and returns `500`. The existing test
`app/tests/test_api_query.py::test_query_returns_answer_with_mock_llm` fails for this reason — that
failure is **pre-existing and expected**.

**Rules:**
- Do **not** build any UI against `/api/v1/*` (`/query`, `/query/stream`, `/query/conversations/{id}`,
  `/api/v1/documents/*`). Those routes are API-key authenticated and intended for programmatic use.
- Use `POST /workspaces/{ws}/chat` for any workspace-level Q&A instead — it works and returns
  `{ answer, sources, conversation_history }`.
- `/api/v1/query/llm/status` requires `X-API-Key` and is not for the dashboard; the model list is
  hardcoded ([§6.7](#67-model-dropdown-reference-data)).
- Baseline test suite (do not try to "fix" the one failure):
  `cd backend && ../.venv/bin/python -m pytest app/tests -q` → **12 passed, 4 skipped, 1 failed**.

### 14.4 Where `widget.js` is served

| URL | What |
|---|---|
| `GET /widget.js` | Readable source, 15,121 B (14.77 KiB) |
| `GET /widget.min.js` | **Production bundle — 10,219 B (9.98 KiB)**, gzips to **4,168 B** |
| `GET /static/widget.js` | Same files, alias path |
| `GET /static/widget.min.js` | Same files, alias path |

The dashboard must **not** edit or serve the widget. It only *displays* the snippet returned by
`GET .../tokens/{id}/snippet`, which already contains the correct `src`. The snippet points at
`widget.min.js` when the bundle exists, and falls back to `widget.js` if it has not been built.

The bundle is generated and gitignored. Rebuild it with:

```bash
cd /home/jteckz7/Xvec-chat
python backend/scripts/build_widget.py          # build + print the size report
python backend/scripts/build_widget.py --check  # CI gate: non-zero if stale
```

### 14.5 Test the embed widget locally

The widget page must be served over **HTTP from a different port than the API** — that is what makes it
a genuine cross-origin test. Opening the file with `file://` sends `Origin: null` and CORS will reject
it.

```bash
# 1. API must be running on :8000 (see §14.1)

# 2. Create a token and get its snippet from the dashboard
#    (Embed tab → Create token → copy snippet), then:
mkdir -p /tmp/xvec-demo && cd /tmp/xvec-demo

# 3. Write index.html and paste the snippet in, before </body>
cat > index.html <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Test</title></head>
<body><h1>My store</h1>
<!-- paste the snippet from the dashboard here -->
</body></html>
HTML

# 4. Serve it on a different port = a different origin
python3 -m http.server 9000 -d /tmp/xvec-demo

# 5. Open http://localhost:9000/index.html
```

Expected: a bubble bottom-right; clicking it opens the panel with the `welcome_message`; sending a
question returns an answer with citation chips; `Esc` closes; narrowing below 480px switches to the
mobile layout. Check DevTools → Console (no errors) and Network (preflight `OPTIONS /public/chat`
returns `200`, not `400 Disallowed CORS origin`).

Verify the whole flow programmatically first — the widget logic has automated coverage (53 checks on
the source and the minified bundle, plus live end-to-end tests), so a visual regression is the only
thing that needs your eyes.

### 14.6 Token storage

**Store the JWT in memory only — not `localStorage`.** See [§6.2](#62-jwt-storage-and-the-401-flow)
for the module and the mandatory 401 handling. There is **no refresh token**; the JWT is valid for 7
days and the user re-authenticates when it expires. Consequence to accept: a hard browser refresh
signs the user out. If that proves unacceptable, the correct mitigation is a short-lived
`httpOnly; Secure; SameSite=Lax` refresh cookie — which requires a backend change (a refresh
endpoint), so raise it with the backend team rather than silently reverting to `localStorage`.

Never store the **embed token** in `localStorage`/`sessionStorage` either — the dashboard itself keeps
the full token in component state for the one-time modal only.

### 14.7 CORS in development

The backend is **not** open to all origins for dashboard calls. Dashboard CORS is restricted to the
`ALLOWED_ORIGINS` list in `backend/.env`:

```
http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://192.168.1.27:5173,http://192.168.1.27:3000
```

If your dev server runs on another port, add it and restart the backend. **Only `/public/*` accepts
any origin** — that is by design, because a widget is embedded on arbitrary customer domains.

### 14.8 Backend env vars the dashboard depends on

| Backend variable | Current dev value | Effect on the frontend |
|---|---|---|
| `APP_PUBLIC_URL` | `http://localhost:8000` | The `src` inside the returned snippet. Must be the **browser-reachable** backend URL. |
| `WIDGET_MINIFIED` | `true` | Snippet points at `widget.min.js`. Set `false` for readable source in the snippet. |
| `ALLOWED_ORIGINS` | see §14.7 | Dashboard CORS allowlist. |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | JWT lifetime. |
| `OPENROUTER_API_KEY` | *(secret)* | Server-side only. **Never** expose it via a `NEXT_PUBLIC_*` variable. |

### 14.9 Definition of done

- [ ] All 32 desktop screens and 4 mobile screens implemented
- [ ] Register → workspace → upload → train → agent → token → snippet → live widget, end to end
- [ ] `widget.js` copied from the snippet actually renders on `http://localhost:9000`
- [ ] Training poll: stops on `ready`/`failed`, survives a network blip, no duplicate toasts
- [ ] A forced JWT expiry mid-session redirects to login with a `?redirect=` back-link
- [ ] The one-time token modal cannot be dismissed without a copy warning
- [ ] Zero `localStorage`/`sessionStorage` usage for the JWT or embed tokens
- [ ] Revoke immediately makes `/public/chat` return `403`
- [ ] No paginator anywhere; no sort control on conversations
- [ ] `sources: []` renders the grounding warning, not an error
- [ ] Zero `dangerouslySetInnerHTML`
- [ ] Bundle budget met: initial ≤ 150 KB gzip, largest route ≤ 80 KB gzip
- [ ] Keyboard-only pass over every screen; axe/Lighthouse WCAG AA clean
- [ ] `npm run build` produces no type errors under `strict`

---

## 15. Appendix A — Verified API Reference

Every response shape below was captured from the **running backend** on 2026-10-01. Use this over
any summary.

### 15.1 Auth

| Endpoint | Body | Success | Errors |
|---|---|---|---|
| `POST /auth/register` | `{email, password}` — email `maxLength=255`, password `minLength=8` | **201** `{access_token, token_type:"bearer", user_id}` | `400 {"detail":"Email already registered"}`, `422` array |
| `POST /auth/login` | `{email, password}` | **200** `TokenResponse` | `401 {"detail":"Invalid credentials"}` |

JWT payload contains **only** `sub` and `exp`. Lifetime `ACCESS_TOKEN_EXPIRE_DAYS = 7`. No refresh
token.

### 15.2 Workspaces

| Endpoint | Success | Errors |
|---|---|---|
| `POST /workspaces` | **201** `{id, name, description, system_prompt, owner_id, created_at}` — `name` 1–100; `system_prompt` defaults to `"You are a helpful assistant."` | `422` |
| `GET /workspaces` | **200** `Workspace[]` | `401` |
| `GET /workspaces/{id}` | **200** `Workspace` | `404 {"detail":"Workspace not found"}` |
| `PUT /workspaces/{id}` | **200** `Workspace` (partial; `null` values ignored) | `404`, `422` |
| `DELETE /workspaces/{id}` | **204** (empty body) | `404` |

`Workspace` has **no `updated_at`**.

### 15.3 Documents

| Endpoint | Success | Errors |
|---|---|---|
| `POST /workspaces/{ws}/documents` | **201** `WorkspaceDocument` — `multipart/form-data`, field **`file`**, extensions `.pdf` `.txt` `.docx` | `400 {"detail":"Unsupported file type '<ext>'. Allowed: .pdf, .txt, .docx"}`, `404` |
| `GET /workspaces/{ws}/documents` | **200** `WorkspaceDocument[]` (`[]` when empty) | `401`, `404` |
| `DELETE /workspaces/{ws}/documents/{doc_id}` | **204** | `404` |
| `POST /workspaces/{ws}/documents/{doc_id}/train` | **202** `{status:"processing", message}` · **200** `{status:"ready", message}` when already trained | `404`, **`409`** already processing |
| `GET /workspaces/{ws}/documents/{doc_id}/status` | **200** `{doc_id, filename, status, chunk_count}` | `404` |

There is **no `GET` for a single document**, no rename endpoint, and **no server-side size cap** on
this route.

### 15.4 Workspace chat

`POST /workspaces/{ws}/chat` → **200** `{answer, sources: Source[], conversation_history: [{role, content}]}`
`message` 1–4000. No `conversation_id`; the caller manages history. No documents ⇒ `sources: []`.

### 15.5 Agents

| Endpoint | Success | Errors |
|---|---|---|
| `POST /workspaces/{ws}/agents` | **201** `Agent` | `422` |
| `GET /workspaces/{ws}/agents` | **200** `Agent[]` | `401`, `404` |
| `GET /workspaces/{ws}/agents/{agent_id}` | **200** `Agent` | `404 {"detail":"Agent not found"}` |
| `PUT /workspaces/{ws}/agents/{agent_id}` | **200** `Agent` | `404`, `422` |
| `DELETE /workspaces/{ws}/agents/{agent_id}` | **204** | `404` |

`Agent` → `{id, workspace_id, name, description, system_prompt, welcome_message, model, temperature,
language, is_active, created_at, updated_at}`.

⚠️ **`is_active` is the integer `0 | 1`**, not a boolean. `welcome_message` is `null` when unset.
`model` defaults to `meta-llama/llama-3.1-8b-instruct`. Unknown `model` or `language` values are
**silently coerced** by the backend's config validator. `PUT` **ignores `null`** — see
[§9.11](#911-field-update-semantics-surprising-must-be-handled). `workspace_id` cannot be changed.

### 15.6 Agent chat & conversations

| Endpoint | Success | Errors |
|---|---|---|
| `POST /workspaces/{ws}/agents/{agent_id}/chat` | **200** `{conversation_id, answer, sources, model_used}` — `message` 1–4000, `conversation_id` optional | `403` (agent inactive), `429` |
| `POST /workspaces/{ws}/agents/{agent_id}/conversations/new` | **201** `{id, agent_id, title, created_at, updated_at}` | `404` |
| `GET /workspaces/{ws}/agents/{agent_id}/conversations` | **200** `Conversation[]` | `404` |
| `GET /workspaces/{ws}/agents/{agent_id}/conversations/{conv_id}` | **200** `{conversation, messages}` | `404` |
| `DELETE /workspaces/{ws}/agents/{agent_id}/conversations/{conv_id}` | **204** | `404` |

A new conversation's `title` is `"New Conversation"`, then auto-titled from the first user message.

### 15.7 Embed tokens

| Endpoint | Success | Errors |
|---|---|---|
| `POST /workspaces/{ws}/agents/{agent_id}/tokens` | **201** `EmbedToken` **with the full token** — `label` 1–100 required | `422` |
| `GET /workspaces/{ws}/agents/{agent_id}/tokens` | **200** `EmbedToken[]`, `token` **masked** | `404` |
| `GET /workspaces/{ws}/agents/{agent_id}/tokens/{token_id}` | **200** `EmbedToken`, masked | `404` |
| `PUT /workspaces/{ws}/agents/{agent_id}/tokens/{token_id}` | **200** `EmbedToken` — `{label?, allowed_origins?, is_active?}` | `404`, `422` |
| `DELETE /workspaces/{ws}/agents/{agent_id}/tokens/{token_id}` | **204** | `404` |
| `GET /workspaces/{ws}/agents/{agent_id}/tokens/{token_id}/snippet` | **200** `{snippet, token}` — **both full** | `404` |

`EmbedToken` → `{id, agent_id, token, label, is_active, allowed_origins, request_count, created_at,
last_used_at}`. ⚠️ **`is_active` is a real boolean here** (unlike `Agent`). Token values are
`secrets.token_hex(32)` = 64 hex characters. `allowed_origins: null` = any origin. Origin matching is
**exact hostname**; localhost is always allowed; a `null` Origin header is rejected.

`request_count` increments on **every** resolved-token call, including the widget's agent-info fetch.

### 15.8 Public (widget) — no auth

| Endpoint | Success | Errors |
|---|---|---|
| `GET /public/agent/{token}` | **200** `{name, description, language, welcome_message}` | `401 {"detail":"Invalid embed token."}`, `403` revoked / agent inactive |
| `POST /public/chat` | **200** `{answer, sources, conversation_id}` — `message` 1–4000 | `401`, `403`, `422`, **`429`** |

**Rate limit: 20 requests / 60 s per embed token**, enforced in-process. On `429` the body is
`{"detail":"Rate limit exceeded. Please slow down."}` and **no `Retry-After` header is sent** — the
client cannot back off intelligently; it must guess. Rate limiting applies to `/public/chat` only.

`/public/*` responses carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
`Referrer-Policy: strict-origin-when-cross-origin`, and permissive CORS (any origin, **no**
`Access-Control-Allow-Credentials`).

### 15.9 Health

| Endpoint | Response |
|---|---|
| `GET /health` | `200 {status:"ok", app, version, timestamp, uptime_seconds}` |
| `GET /health/ready` | `200 {status:"ready", database:"ok", timestamp}` |

### 15.10 Error catalogue (for the message map in [§6.1](#61-error-shape-normalisation))

| Code | `detail` | Where | Suggested user copy |
|---|---|---|---|
| 400 | `"Email already registered"` | register | "That email is already registered." |
| 400 | `"Unsupported file type '<ext>'. Allowed: .pdf, .txt, .docx"` | upload | Show verbatim |
| 401 | `"Invalid credentials"` | login | "Invalid email or password." |
| 401 | `"Invalid or expired token"` | any JWT route | Trigger the 401 flow |
| 401 | `"Invalid embed token."` | `/public/*` | Widget-side only |
| 403 | `"This embed token has been revoked."` | `/public/chat` | Widget-side only |
| 403 | `"Origin {origin} is not authorised for this widget."` | `/public/chat` | Widget-side only |
| 403 | `"Agent is not available."` | `/public/*` | Widget-side only |
| 404 | `"Workspace not found"` / `"Agent not found"` / `"Conversation not found"` | detail routes | Dedicated not-found page |
| 409 | (train in progress) | `train` | Suppress; existing poll continues |
| 422 | array of `{type, loc, msg, input, ctx}` | any validation | Map to fields |
| 429 | `"Rate limit exceeded. Please slow down."` | `/public/chat` | Widget-side only |

---

## 16. Appendix B — Corrections to the Original API Brief

The brief this document was written from contained several inaccuracies. **The verified behaviour in
this document is authoritative.** Listed here so nobody re-introduces the original values.

| # | Original brief said | Reality | Impact if unfixed |
|---|---|---|---|
| 1 | Agent `model` default `"meta-llama/llama-3.3-70b-instruct:free"` | Default is **`meta-llama/llama-3.1-8b-instruct`**. All three pinned `:free` models now 404 upstream and `openrouter/free` is quota-limited. | The default model could not answer at all; every new agent 500s on chat. |
| 2 | "There is no API that lists models" — implied but not stated | Correct, and `AgentCreate.model`/language are **silently coerced** when unrecognised. | Hardcoding a bad list silently rewrites the user's choice. |
| 3 | `POST .../conversations/new` → `200` | Returns **`201`** | Treating 201 as an error path. |
| 4 | `Agent.is_active: 0 \| 1` and `EmbedToken.is_active: 0 \| 1` | Agent returns an **integer** `0\|1`; embed token returns a **boolean** | `=== false` checks silently fail on agents. |
| 5 | `EmbedToken.token` "masked `a3f7c91b...`" | Masked value is **11 characters** (`first 8` + `...`) | Length-based UI logic breaks. |
| 6 | Register returns `201` with `400` for a duplicate email | Confirmed correct | — |
| 7 | Documents: `.pdf, .txt, .docx` | Confirmed correct. But **no server-side size cap** on the workspace route (the 50 MB cap is on the API-key route only). | Users upload 300 MB files and watch the request die. |
| 8 | "Token expires after 7 days" | Correct (`ACCESS_TOKEN_EXPIRE_DAYS=7`), but the JWT has **no `iat`** and there is **no refresh token**. | Counting down the session is impossible and misleading. |
| 9 | Implied the dashboard CORS allows any origin in dev | Dashboard CORS is **restricted** to an `ALLOWED_ORIGINS` list; only `/public/*` accepts any origin. | Every dashboard request fails with `net::ERR_FAILED` on an unlisted port. |
| 10 | `PUT` described as a normal partial update | The backend **ignores `null`** values on update. | "Clear this field" appears broken. |
| 11 | `POST /workspaces/{id}/chat` described as the Phase 2 chat | Correct and working — this is the endpoint to use, since `POST /api/v1/query` is broken | — |
| 12 | Rate limit "20 req/min per token" | Correct (20 / 60 s), but **only** on `/public/chat`, with **no `Retry-After` header** | Back-off logic can't be correct. |
| 13 | Timestamps implied to be standard ISO with offset | Returned as **naive ISO** (no `Z`/offset) — UTC | Parsed as local time → wrong times shown. |
| 14 | `Workspace` object | Has **no `updated_at`** | Render an undefined "last updated". |
| 15 | Origin restrictions described as a simple allow-list | Exact **hostname** match; `www.` is a different host; localhost always allowed; `null` Origin rejected | `mystore.co.tz` configured → `www.mystore.co.tz` breaks silently. |

**Unchanged and confirmed correct from the brief:** the auth contract and error codes, the workspace
CRUD surface, document upload/train/status including `409`, the agent CRUD surface, agent chat and
conversation endpoints, the six embed-token endpoints and the one-time-token rule, the public
endpoint response shapes, the health endpoints, `.pdf/.txt/.docx`, and the 7-day token lifetime.
