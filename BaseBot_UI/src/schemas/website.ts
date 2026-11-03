import { z } from "zod";

export const websiteSourceStatusSchema = z.enum([
  "pending",
  "syncing",
  "synced",
  "failed",
]);

export const websitePageStatusSchema = z.enum([
  "discovered",
  "indexed",
  "failed",
  "removed",
]);

export const websiteRefreshPolicySchema = z.enum(["manual", "weekly", "daily"]);

export const websiteSourceSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  url: z.string(),
  name: z.string(),
  status: websiteSourceStatusSchema,
  pages_discovered: z.number(),
  pages_indexed: z.number(),
  last_synced_at: z.string().nullable(),
  next_sync_at: z.string().nullable(),
  refresh_policy: websiteRefreshPolicySchema,
  error_message: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const websiteSourceListSchema = z.array(websiteSourceSchema);

export const websitePageSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  workspace_id: z.string(),
  url: z.string(),
  title: z.string().nullable(),
  content_hash: z.string().nullable(),
  status: websitePageStatusSchema,
  chunk_count: z.number(),
  error_message: z.string().nullable(),
  last_indexed_at: z.string().nullable(),
  created_at: z.string(),
});

export const websitePageListSchema = z.array(websitePageSchema);

/**
 * Users type "example.com" far more often than a full URL. Prefix HTTPS before
 * validating so the form behaves the way browsers do; the backend still
 * performs the authoritative scheme, DNS and SSRF checks.
 */
export function toAbsoluteWebsiteUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("//")) return `https:${trimmed}`;
  return `https://${trimmed}`;
}

const BLOCKED_HOST_SUFFIXES = [
  ".localhost",
  ".local",
  ".internal",
  ".home",
  ".lan",
  ".corp",
];

/** Client-side pre-flight only. The backend owns the real security boundary. */
export function websiteUrlError(value: string): string | null {
  const candidate = toAbsoluteWebsiteUrl(value);
  if (!candidate) return "Enter a website address.";
  if (candidate.length > 2048) {
    return "Website addresses can be at most 2048 characters.";
  }
  if (/[\u0000-\u0020\u007f]/.test(candidate)) {
    return "Remove spaces and control characters from the address.";
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return "Enter a valid website address, like https://example.com.";
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http:// and https:// websites are supported.";
  }
  if (parsed.username || parsed.password) {
    return "Website addresses cannot contain usernames or passwords.";
  }
  if (!parsed.hostname) {
    return "Enter a valid website address, like https://example.com.";
  }

  const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
  if (
    host === "localhost" ||
    BLOCKED_HOST_SUFFIXES.some((suffix) => host.endsWith(suffix))
  ) {
    return "Enter a public website address — private and local addresses cannot be crawled.";
  }
  if (!host.includes(".") && !host.startsWith("[")) {
    return "Enter a public website address, like https://example.com.";
  }

  return null;
}

export const websiteFormSchema = z.object({
  url: z
    .string()
    .trim()
    .min(1, "Enter a website address.")
    .max(2048, "Website addresses can be at most 2048 characters.")
    .superRefine((value, ctx) => {
      const issue = websiteUrlError(value);
      if (issue) ctx.addIssue({ code: "custom", message: issue });
    }),
  name: z
    .string()
    .trim()
    .max(100, "Use 100 characters or fewer for the display name.")
    .optional(),
  refresh_policy: websiteRefreshPolicySchema,
});

export type WebsiteFormValues = z.infer<typeof websiteFormSchema>;

/** Canonical form used in the API request. */
export function normaliseWebsiteFormUrl(value: string): string {
  const parsed = new URL(toAbsoluteWebsiteUrl(value));
  parsed.hash = "";
  return parsed.toString();
}
