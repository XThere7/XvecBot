import type { Plan } from "@/types/api";

export type PlanHighlight = {
  label: string;
  /** Advertised in this tier but not built yet. */
  soon?: boolean;
};

function storageLabel(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${bytes / 1024 ** 3} GB`;
  if (bytes >= 1024 ** 2) return `${bytes / 1024 ** 2} MB`;
  return `${bytes} B`;
}

function numberLabel(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function countLabel(
  value: number | null,
  singular: string,
  plural = `${singular}s`,
): string {
  if (value === null) return `Unlimited ${plural}`;
  return `${numberLabel(value)} ${value === 1 ? singular : plural}`;
}

function refreshLabel(value: Plan["limits"]["website_refresh"]): string {
  if (value === "daily") return "Daily website refresh";
  if (value === "weekly") return "Weekly website refresh";
  return "Manual website refresh";
}

/**
 * Marketing copy for each tier. Numeric limits always come from the API plan
 * object so the pricing page can never drift from what the backend enforces.
 */
export function planHighlights(plan: Plan): PlanHighlight[] {
  const soon = new Set(plan.coming_soon);
  const item = (label: string, key?: string): PlanHighlight =>
    key && soon.has(key) ? { label, soon: true } : { label };
  const { limits } = plan;

  const core = [
    { label: countLabel(limits.agents, "AI agent") },
    { label: `${countLabel(limits.documents, "document")} / workspace` },
    { label: `${countLabel(limits.pages_indexed, "indexed page")} / workspace` },
    { label: `${countLabel(limits.website_sources, "website source")} / workspace` },
    { label: refreshLabel(limits.website_refresh) },
    {
      label: `${countLabel(
        limits.chat_messages,
        "chat message",
      )} / month`,
    },
    { label: `${countLabel(limits.embed_tokens, "embed token")} / agent` },
    { label: `${storageLabel(limits.storage_bytes)} knowledge storage` },
  ];

  if (plan.id === "free") {
    return [
      ...core,
      item("Website chatbot widget"),
      item("Sources & citations"),
      item("Conversation history"),
      item("Lead collection & forms", "lead_forms"),
    ];
  }

  if (plan.id === "standard") {
    return [
      ...core,
      item(
        countLabel(limits.api_keys, "developer API key"),
        "developer_api",
      ),
      item("Email integration for authorized inboxes", "email_integration"),
      item("Lead qualification & structured forms", "lead_qualification"),
      item("Booking, order & support actions", "actions"),
      item("Basic analytics & usage reports"),
      item(`Up to ${limits.members} members`, "members"),
      { label: "Standard support" },
    ];
  }

  return [
    ...core,
    item("Unlimited developer API keys"),
    item("WhatsApp integration", "whatsapp"),
    item("Advanced actions & automations", "automations"),
    item("Advanced analytics & activity logs", "advanced_analytics"),
    item(`Up to ${limits.members} members`, "members"),
    item("Custom branding", "custom_branding"),
    { label: "Priority support" },
  ];
}

export const PLAN_CTA: Record<Plan["id"], string> = {
  free: "Start free",
  standard: "Choose Standard",
  pro: "Choose Pro",
};

export const PLAN_BLURB: Record<Plan["id"], string> = {
  free: "Start with the essentials and keep a real project running. No card, no expiry.",
  standard:
    "The working plan for a small business that answers customers every day.",
  pro: "Unlimited scale, daily refreshes and the developer API for growing teams.",
};
