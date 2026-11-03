import { z } from "zod";

export const socialMediaPlatformSchema = z.enum([
  "tiktok",
  "instagram",
  "facebook",
]);

export const socialMediaSourceStatusSchema = z.enum([
  "pending",
  "extracting",
  "awaiting_input",
  "ready",
  "indexing",
  "imported",
  "failed",
]);

export const socialMediaSourceSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  agent_id: z.string(),
  url: z.string(),
  normalized_url: z.string(),
  platform: socialMediaPlatformSchema,
  provider_post_id: z.string().nullable(),
  title: z.string().nullable(),
  author_name: z.string().nullable(),
  published_at: z.string().nullable(),
  thumbnail_url: z.string().nullable(),
  content_text: z.string().nullable(),
  content_hash: z.string().nullable(),
  status: socialMediaSourceStatusSchema,
  extraction_method: z.string().nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  chunk_count: z.number(),
  attempt_count: z.number(),
  imported_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const socialMediaUsageSchema = z.object({
  used: z.number(),
  limit: z.number(),
});

export const socialMediaListResponseSchema = z.object({
  sources: z.array(socialMediaSourceSchema),
  usage: socialMediaUsageSchema,
  supported_platforms: z.array(socialMediaPlatformSchema),
  max_content_chars: z.number(),
});

export const socialMediaCreateResponseSchema = z.object({
  source: socialMediaSourceSchema,
  usage: socialMediaUsageSchema,
});

export const socialMediaSyncResponseSchema = z.object({
  sources: z.array(socialMediaSourceSchema),
  queued: z.number(),
});

/** Add https:// when the user pastes a bare platform link. */
export function toAbsoluteMediaUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function mediaUrlError(value: string): string | null {
  const candidate = toAbsoluteMediaUrl(value);
  if (!candidate) return "Paste a public post link.";
  if (candidate.length > 2048) {
    return "Post links can be at most 2048 characters.";
  }
  if (/[\u0000-\u0020\u007f]/.test(candidate)) {
    return "Remove spaces and control characters from the link.";
  }
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return "Enter a valid post link, like https://www.instagram.com/p/…";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http:// and https:// post links are supported.";
  }
  if (parsed.username || parsed.password) {
    return "Post links cannot include usernames or passwords.";
  }
  const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
  const supported =
    host === "tiktok.com" ||
    host.endsWith(".tiktok.com") ||
    host === "instagram.com" ||
    host.endsWith(".instagram.com") ||
    host === "facebook.com" ||
    host.endsWith(".facebook.com") ||
    host === "fb.watch" ||
    host.endsWith(".fb.watch");
  if (!supported) {
    return "Use a public TikTok, Instagram or Facebook post link.";
  }
  return null;
}

export function normaliseMediaInput(value: string): string {
  const parsed = new URL(toAbsoluteMediaUrl(value));
  parsed.hash = "";
  return parsed.toString();
}

export const mediaFormSchema = z.object({
  url: z
    .string()
    .trim()
    .min(1, "Paste a public post link.")
    .max(2048, "Post links can be at most 2048 characters.")
    .superRefine((value, ctx) => {
      const issue = mediaUrlError(value);
      if (issue) ctx.addIssue({ code: "custom", message: issue });
    }),
});

export type MediaFormValues = z.infer<typeof mediaFormSchema>;
