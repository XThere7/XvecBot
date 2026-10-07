import { z } from "zod";
import { MAX_LABEL_LENGTH } from "@/lib/constants";

export const ORIGIN_HELPER =
  "Leave empty to allow the widget on any domain. Add hostnames to lock it down — matching is exact, so `mystore.co.tz` and `www.mystore.co.tz` are different entries.";

export const tokenFormSchema = z.object({
  label: z
    .string()
    .trim()
    .min(1, "Give the token a label so you recognise it later.")
    .max(MAX_LABEL_LENGTH, `Keep the label under ${MAX_LABEL_LENGTH} characters.`),
  allowed_origins: z.array(z.string()).default([]),
});

export type TokenFormValues = z.infer<typeof tokenFormSchema>;

export const TOKEN_FORM_DEFAULTS: TokenFormValues = {
  label: "",
  allowed_origins: [],
};

export const embedTokenSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  token: z.string(),
  label: z.string(),
  is_active: z.boolean(),
  allowed_origins: z.array(z.string()).nullable(),
  request_count: z.number(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
});

export const embedTokenListSchema = z.array(embedTokenSchema);

export const embedSnippetSchema = z.object({
  snippet: z.string(),
  token: z.string(),
});

/**
 * Origins must be bare hostnames. Strip protocol, credentials, trailing slash
 * and path client-side so what the user typed and what we send agree.
 */
export function normaliseOrigin(input: string): string | null {
  let value = input.trim().toLowerCase();
  if (!value) return null;
  value = value.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
  value = value.replace(/^[^@/]*@/, "");
  value = value.split("/")[0] ?? "";
  value = value.replace(/:(\d+)$/, "");
  if (!value) return null;
  if (!/^[a-z0-9.-]+$/.test(value)) return null;
  return value;
}

export function isValidOrigin(input: string): boolean {
  return normaliseOrigin(input) !== null;
}