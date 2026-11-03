/**
 * Minimal in-memory mock of the BotBase backend, matching the verified shapes in
 * frontendbot.md Appendix A. Used only for local smoke testing of the dashboard.
 *
 *   node mock-api.mjs [port]
 */
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";

const PORT = Number(process.argv[2] ?? 8000);

const users = new Map();
const workspaces = new Map();
const documents = new Map();
const websites = new Map();
const websitePages = new Map();
const agents = new Map();
const conversations = new Map();
const messages = new Map();
const tokens = new Map();

const now = () => new Date().toISOString().replace("Z", "");

const FREE_PLAN = {
  id: "free",
  name: "Free",
  tagline: "For trying BotBase on one workspace.",
  price_tzs: 0,
  price_label: "Free",
  price_display: "Free forever",
  period: "forever",
  recommended: false,
  limits: {
    agents: 1,
    documents: 5,
    pages_indexed: 50,
    website_sources: 1,
    website_refresh: "manual",
    api_keys: 0,
    chat_messages: 100,
    embed_tokens: 1,
    storage_bytes: 100 * 1024 * 1024,
    members: 1,
    social_media_sources: 3,
  },
  features: {
    website_widget: true,
    citations: true,
    conversation_history: true,
    lead_forms: false,
    email_integration: false,
    lead_qualification: false,
    actions: false,
    analytics: "usage",
    whatsapp: false,
    developer_api: false,
    automations: false,
    custom_branding: false,
    support: "community",
  },
  coming_soon: ["lead_forms"],
};

function billingFor(workspace) {
  const storageUsed = [...documents.values()]
    .filter((document) => document.workspace_id === workspace.id)
    .reduce((total, document) => total + document.size_bytes, 0);
  const agentCount = [...agents.values()].filter(
    (agent) => agent.workspace_id === workspace.id,
  ).length;
  const nowIso = now();
  const counter = (used, limit) => ({
    used,
    limit,
    percent: limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0,
    unlimited: limit === null,
  });

  return {
    workspace_id: workspace.id,
    plan: FREE_PLAN,
    plans: [FREE_PLAN],
    is_trial: false,
    base_plan: "free",
    effective_plan: "free",
    trial_ends_at: null,
    days_remaining: null,
    usage: {
      agents: counter(agentCount, FREE_PLAN.limits.agents),
      documents: counter(
        [...documents.values()].filter((d) => d.workspace_id === workspace.id)
          .length,
        FREE_PLAN.limits.documents,
      ),
      pages_indexed: counter(0, FREE_PLAN.limits.pages_indexed),
      website_sources: counter(
        [...websites.values()].filter((w) => w.workspace_id === workspace.id)
          .length,
        FREE_PLAN.limits.website_sources,
      ),
      api_keys: counter(0, FREE_PLAN.limits.api_keys),
      embed_tokens: counter(
        [...tokens.values()].filter((t) => t.workspace_id === workspace.id)
          .length,
        FREE_PLAN.limits.embed_tokens,
      ),
      chat_messages: {
        ...counter(0, FREE_PLAN.limits.chat_messages),
        period_start: nowIso,
        period_end: nowIso,
        resets_at: nowIso,
      },
      storage: {
        used_bytes: storageUsed,
        limit_bytes: FREE_PLAN.limits.storage_bytes,
        percent: Math.min(
          100,
          Math.round((storageUsed / FREE_PLAN.limits.storage_bytes) * 100),
        ),
      },
      members: { ...counter(1, FREE_PLAN.limits.members), enforced: true },
    },
    period: { start: nowIso, end: nowIso, resets_at: nowIso },
    plan_started_at: workspace.plan_started_at,
    payments_configured: false,
    upgrade_available: false,
    launch_note: "Payments are not configured in this mock.",
  };
}

function finishWebsiteSync(source) {
  for (const [id, page] of websitePages) {
    if (page.source_id === source.id) websitePages.delete(id);
  }

  const origin = new URL(source.url).origin;
  const pages = [
    { path: "/", title: "Home" },
    { path: "/about", title: "About us" },
    { path: "/pricing", title: "Pricing" },
  ];
  for (const [index, page] of pages.entries()) {
    const id = randomUUID();
    websitePages.set(id, {
      id,
      source_id: source.id,
      workspace_id: source.workspace_id,
      url: `${origin}${page.path}`,
      title: page.title,
      content_hash: `hash-${index + 1}`,
      status: "indexed",
      chunk_count: 4,
      error_message: null,
      last_indexed_at: now(),
      created_at: now(),
    });
  }

  source.status = "synced";
  source.pages_discovered = pages.length;
  source.pages_indexed = pages.length;
  source.last_synced_at = now();
  source.next_sync_at = null;
  source.error_message = null;
  source.updated_at = now();
}

function token64() {
  return Array.from({ length: 64 }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join("");
}

let ORIGIN = "http://localhost:3000";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": ORIGIN,
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    Vary: "Origin",
  };
}

function send(res, status, body) {
  if (status === 204) {
    res.writeHead(204, corsHeaders());
    res.end();
    return;
  }
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    ...corsHeaders(),
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

function auth(req) {
  const header = req.headers.authorization ?? "";
  const value = header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!value) return null;
  for (const [email, user] of users) {
    if (user.token === value) return { email, ...user };
  }
  return null;
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname.replace(/\/$/, "");
  const method = req.method ?? "GET";

  ORIGIN = req.headers.origin ?? ORIGIN;
  if (method === "OPTIONS") return send(res, 204);

  if (path === "/auth/register" && method === "POST") {
    const body = JSON.parse((await readBody(req)).toString() || "{}");
    if (!body.email || !body.password) return send(res, 422, { detail: [] });
    if (body.password.length < 8) {
      return send(res, 422, {
        detail: [
          {
            type: "string_too_short",
            loc: ["body", "password"],
            msg: "String should have at least 8 characters",
          },
        ],
      });
    }
    if (users.has(body.email)) {
      return send(res, 400, { detail: "Email already registered" });
    }
    const user = { userId: randomUUID(), password: body.password, token: `tok-${randomUUID()}` };
    users.set(body.email, user);
    return send(res, 201, {
      access_token: user.token,
      token_type: "bearer",
      user_id: user.userId,
    });
  }

  if (path === "/auth/login" && method === "POST") {
    const body = JSON.parse((await readBody(req)).toString() || "{}");
    const user = users.get(body.email);
    if (!user || user.password !== body.password) {
      return send(res, 401, { detail: "Invalid credentials" });
    }
    return send(res, 200, {
      access_token: user.token,
      token_type: "bearer",
      user_id: user.userId,
    });
  }

  if (path === "/health") return send(res, 200, { status: "ok" });

  const parts = path.split("/").filter(Boolean);
  if (!path.startsWith("/workspaces")) return send(res, 404, { detail: "Not found" });
  if (!auth(req)) return send(res, 401, { detail: "Invalid or expired token" });

  const wsId = parts[1];

  if (parts.length === 1 && method === "GET") {
    const owner = auth(req).userId;
    return send(res, 200, [...workspaces.values()].filter((w) => w.owner_id === owner));
  }

  if (parts.length === 1 && method === "POST") {
    const body = JSON.parse((await readBody(req)).toString() || "{}");
    if (!body.name) {
      return send(res, 422, {
        detail: [
          { type: "string_too_short", loc: ["body", "name"], msg: "String should have at least 1 character" },
        ],
      });
    }
    const workspace = {
      id: randomUUID(),
      name: body.name,
      description: body.description ?? null,
      system_prompt: body.system_prompt ?? "You are a helpful assistant.",
      owner_id: auth(req).userId,
      created_at: now(),
      plan: "free",
      plan_started_at: null,
    };
    workspaces.set(workspace.id, workspace);
    return send(res, 201, workspace);
  }

  const workspace = workspaces.get(wsId);
  if (!workspace || workspace.owner_id !== auth(req).userId) {
    return send(res, 404, { detail: "Workspace not found" });
  }

  if (parts.length === 2) {
    if (method === "GET") return send(res, 200, workspace);
    if (method === "PUT") {
      const body = JSON.parse((await readBody(req)).toString() || "{}");
      for (const [key, value] of Object.entries(body)) {
        if (value === null) continue;
        workspace[key] = value;
      }
      return send(res, 200, workspace);
    }
    if (method === "DELETE") {
      workspaces.delete(wsId);
      for (const [id, doc] of documents) if (doc.workspace_id === wsId) documents.delete(id);
      for (const [id, source] of websites) if (source.workspace_id === wsId) websites.delete(id);
      for (const [id, page] of websitePages) if (page.workspace_id === wsId) websitePages.delete(id);
      for (const [id, agent] of agents) if (agent.workspace_id === wsId) agents.delete(id);
      return send(res, 204);
    }
  }

  if (parts.length === 3 && parts[2] === "billing" && method === "GET") {
    return send(res, 200, billingFor(workspace));
  }

  if (parts.length === 3 && parts[2] === "chat" && method === "POST") {
    const body = JSON.parse((await readBody(req)).toString() || "{}");
    const docs = [...documents.values()].filter((d) => d.workspace_id === wsId && d.status === "ready");
    return send(res, 200, {
      answer: docs.length
        ? `Based on ${docs[0].filename}, here is the answer.`
        : "I have no documents to answer from yet.",
      sources: docs.length ? [{ filename: docs[0].filename, chunk_index: 0 }] : [],
      conversation_history: body.conversation_history ?? [],
    });
  }

  if (parts[2] === "websites") {
    if (parts.length === 3 && method === "GET") {
      return send(
        res,
        200,
        [...websites.values()]
          .filter((source) => source.workspace_id === wsId)
          .sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
      );
    }

    if (parts.length === 3 && method === "POST") {
      const body = JSON.parse((await readBody(req)).toString() || "{}");
      let parsed;
      try {
        parsed = new URL(body.url);
      } catch {
        return send(res, 400, { detail: "Invalid URL format." });
      }
      if (!["http:", "https:"].includes(parsed.protocol)) {
        return send(res, 400, {
          detail: "Only http:// and https:// URLs are supported.",
        });
      }
      const url = parsed.toString();
      const duplicate = [...websites.values()].some(
        (source) => source.workspace_id === wsId && source.url === url,
      );
      if (duplicate) {
        return send(res, 409, {
          detail: "This website is already connected to the workspace.",
        });
      }

      const source = {
        id: randomUUID(),
        workspace_id: wsId,
        url,
        name: body.name?.trim() || parsed.hostname.replace(/^www\./, ""),
        status: "syncing",
        pages_discovered: 0,
        pages_indexed: 0,
        last_synced_at: null,
        next_sync_at: null,
        refresh_policy: body.refresh_policy ?? "manual",
        error_message: null,
        created_at: now(),
        updated_at: now(),
      };
      websites.set(source.id, source);
      setTimeout(() => finishWebsiteSync(source), 2500);
      return send(res, 202, source);
    }

    const source = websites.get(parts[3]);
    if (!source || source.workspace_id !== wsId) {
      return send(res, 404, { detail: "Website source not found" });
    }

    if (parts.length === 4 && method === "GET") return send(res, 200, source);

    if (parts.length === 4 && method === "DELETE") {
      if (source.status === "syncing") {
        return send(res, 409, {
          detail: "Cannot delete a source while it is syncing.",
        });
      }
      websites.delete(source.id);
      for (const [id, page] of websitePages) {
        if (page.source_id === source.id) websitePages.delete(id);
      }
      return send(res, 204);
    }

    if (parts[4] === "pages" && method === "GET") {
      return send(
        res,
        200,
        [...websitePages.values()].filter((page) => page.source_id === source.id),
      );
    }

    if (parts[4] === "refresh" && method === "POST") {
      if (source.status === "syncing") {
        return send(res, 409, { detail: "A sync is already in progress." });
      }
      source.status = "syncing";
      source.error_message = null;
      source.updated_at = now();
      setTimeout(() => finishWebsiteSync(source), 2500);
      return send(res, 202, { message: "Refresh started." });
    }
  }

  if (parts[2] === "documents") {
    if (parts.length === 3 && method === "GET") {
      return send(res, 200, [...documents.values()].filter((d) => d.workspace_id === wsId));
    }
    if (parts.length === 3 && method === "POST") {
      const raw = await readBody(req);
      const filename = /filename="([^"]+)"/.exec(raw.toString("latin1"))?.[1] ?? "unknown.pdf";
      const ext = filename.split(".").pop().toLowerCase();
      if (!["pdf", "txt", "docx"].includes(ext)) {
        return send(res, 400, {
          detail: `Unsupported file type '.${ext}'. Allowed: .pdf, .txt, .docx`,
        });
      }
      const doc = {
        id: randomUUID(),
        workspace_id: wsId,
        filename,
        file_type: ext,
        size_bytes: raw.length,
        status: "uploaded",
        chunk_count: 0,
        created_at: now(),
      };
      documents.set(doc.id, doc);
      setTimeout(() => {
        doc.status = "ready";
        doc.chunk_count = 12;
      }, 4000);
      return send(res, 201, doc);
    }
    const doc = documents.get(parts[3]);
    if (!doc) return send(res, 404, { detail: "Document not found" });

    if (parts[4] === "train" && method === "POST") {
      if (doc.status === "processing") return send(res, 409, { detail: "Training already in progress" });
      if (doc.status === "ready") return send(res, 200, { status: "ready", message: "Already trained" });
      doc.status = "processing";
      setTimeout(() => {
        doc.status = "ready";
        doc.chunk_count = 12;
      }, 4000);
      return send(res, 202, { status: "processing", message: "Training started" });
    }
    if (parts[4] === "status" && method === "GET") {
      return send(res, 200, {
        doc_id: doc.id,
        filename: doc.filename,
        status: doc.status,
        chunk_count: doc.chunk_count,
      });
    }
    if (parts.length === 4 && method === "DELETE") {
      documents.delete(doc.id);
      return send(res, 204);
    }
  }

  if (parts[2] === "agents") {
    if (parts.length === 3 && method === "GET") {
      return send(res, 200, [...agents.values()].filter((a) => a.workspace_id === wsId));
    }
    if (parts.length === 3 && method === "POST") {
      const body = JSON.parse((await readBody(req)).toString() || "{}");
      if (!body.name || !body.system_prompt) {
        return send(res, 422, {
          detail: [
            {
              type: "string_too_short",
              loc: ["body", body.name ? "system_prompt" : "name"],
              msg: "Field required",
            },
          ],
        });
      }
      const agent = {
        id: randomUUID(),
        workspace_id: wsId,
        name: body.name,
        description: body.description ?? null,
        system_prompt: body.system_prompt,
        welcome_message: body.welcome_message ?? null,
        icon_url: null,
        model: body.model ?? "meta-llama/llama-3.1-8b-instruct",
        temperature: body.temperature ?? 0.7,
        language: body.language ?? "English",
        is_active: 1,
        created_at: now(),
        updated_at: now(),
      };
      agents.set(agent.id, agent);
      return send(res, 201, agent);
    }

    const agent = agents.get(parts[3]);
    if (!agent) return send(res, 404, { detail: "Agent not found" });

    if (parts.length === 4 && method === "GET") return send(res, 200, agent);
    if (parts.length === 4 && method === "PUT") {
      const body = JSON.parse((await readBody(req)).toString() || "{}");
      for (const [key, value] of Object.entries(body)) {
        if (value === null) continue;
        agent[key] = value;
      }
      agent.updated_at = now();
      return send(res, 200, agent);
    }
    if (parts.length === 4 && method === "DELETE") {
      agents.delete(agent.id);
      for (const [id, conv] of conversations) if (conv.agent_id === agent.id) conversations.delete(id);
      for (const [id, t] of tokens) if (t.agent_id === agent.id) tokens.delete(id);
      return send(res, 204);
    }

    if (parts[4] === "chat" && method === "POST") {
      if (!agent.is_active) return send(res, 403, { detail: "Agent is not available." });
      const body = JSON.parse((await readBody(req)).toString() || "{}");
      let conversationId = body.conversation_id;
      if (!conversationId) {
        conversationId = randomUUID();
        conversations.set(conversationId, {
          id: conversationId,
          agent_id: agent.id,
          title: "New Conversation",
          created_at: now(),
          updated_at: now(),
        });
        messages.set(conversationId, []);
      }
      const thread = messages.get(conversationId) ?? [];
      thread.push({
        id: randomUUID(),
        conversation_id: conversationId,
        role: "user",
        content: body.message,
        sources: null,
        created_at: now(),
      });
      const readyDocs = [...documents.values()].filter(
        (document) => document.workspace_id === wsId && document.status === "ready",
      );
      const indexedPages = [...websitePages.values()].filter(
        (page) => page.workspace_id === wsId && page.status === "indexed",
      );
      const websiteCitation =
        indexedPages.find((page) => page.title?.toLowerCase().includes("pricing")) ??
        indexedPages[0];
      const grounded =
        body.message.toLowerCase().includes("price") &&
        (readyDocs.length > 0 || Boolean(websiteCitation));
      const sources = grounded
        ? readyDocs.length > 0
          ? [{ filename: readyDocs[0].filename, chunk_index: 3 }]
          : [
              {
                filename: websiteCitation.title ?? websiteCitation.url,
                chunk_index: 0,
                source_url: websiteCitation.url,
              },
            ]
        : [];
      thread.push({
        id: randomUUID(),
        conversation_id: conversationId,
        role: "assistant",
        content: grounded
          ? readyDocs.length > 0
            ? "Our prices are in the catalogue."
            : "Our prices are on the pricing page."
          : "I am not sure about that.",
        sources,
        created_at: now(),
      });
      messages.set(conversationId, thread);
      const conversation = conversations.get(conversationId);
      conversation.title = body.message.slice(0, 40);
      conversation.updated_at = now();
      return send(res, 200, {
        conversation_id: conversationId,
        answer: grounded
          ? readyDocs.length > 0
            ? "Our prices are in the catalogue."
            : "Our prices are on the pricing page."
          : "I am not sure about that.",
        sources,
        model_used: agent.model,
      });
    }

    if (parts[4] === "conversations") {
      if (parts.length === 5 && method === "GET") {
        return send(res, 200, [...conversations.values()].filter((c) => c.agent_id === agent.id));
      }
      if (parts.length === 5 && method === "POST") {
        const conversation = {
          id: randomUUID(),
          agent_id: agent.id,
          title: "New Conversation",
          created_at: now(),
          updated_at: now(),
        };
        conversations.set(conversation.id, conversation);
        messages.set(conversation.id, []);
        return send(res, 201, conversation);
      }
      const conversation = conversations.get(parts[5]);
      if (!conversation) return send(res, 404, { detail: "Conversation not found" });
      if (parts.length === 6 && method === "GET") {
        return send(res, 200, { conversation, messages: messages.get(conversation.id) ?? [] });
      }
      if (parts.length === 6 && method === "DELETE") {
        conversations.delete(conversation.id);
        messages.delete(conversation.id);
        return send(res, 204);
      }
    }

    if (parts[4] === "tokens") {
      const snippetFor = (token) =>
        `<!-- BotBase chat widget -->\n<script src="http://localhost:${PORT}/widget.min.js"\n        data-agent="${token}"\n        data-position="right"\n        data-color="#6366f1"\n        async></script>`;

      if (parts.length === 5 && method === "GET") {
        // The API masks the token on list: first 8 characters + "…" (11 chars).
        const masked = [...tokens.values()]
          .filter((t) => t.agent_id === agent.id)
          .map((t) => ({ ...t, token: `${t.token.slice(0, 8)}...` }));
        return send(res, 200, masked);
      }
      if (parts.length === 5 && method === "POST") {
        const body = JSON.parse((await readBody(req)).toString() || "{}");
        if (!body.label) {
          return send(res, 422, {
            detail: [{ type: "missing", loc: ["body", "label"], msg: "Field required" }],
          });
        }
        const full = token64();
        const record = {
          id: randomUUID(),
          agent_id: agent.id,
          workspace_id: wsId,
          token: full,
          label: body.label,
          is_active: true,
          allowed_origins: body.allowed_origins ?? null,
          request_count: 0,
          created_at: now(),
          last_used_at: null,
        };
        tokens.set(record.id, record);
        return send(res, 201, record);
      }

      const record = tokens.get(parts[5]);
      if (!record) return send(res, 404, { detail: "Token not found" });
      if (parts.length === 6 && method === "PUT") {
        const body = JSON.parse((await readBody(req)).toString() || "{}");
        for (const [key, value] of Object.entries(body)) {
          if (value === null) continue;
          record[key] = Array.isArray(value) && value.length === 0 ? null : value;
        }
        return send(res, 200, record);
      }
      if (parts.length === 6 && method === "DELETE") {
        tokens.delete(record.id);
        return send(res, 204);
      }
      if (parts[6] === "snippet" && method === "GET") {
        return send(res, 200, {
          snippet: snippetFor(record.token),
          token: record.token,
          hosted_url: `http://localhost:${PORT}/chat/${record.token}`,
        });
      }
    }
  }

  return send(res, 404, { detail: "Not found" });
});

server.listen(PORT, () => {
  console.log(`mock api listening on http://localhost:${PORT}`);
});