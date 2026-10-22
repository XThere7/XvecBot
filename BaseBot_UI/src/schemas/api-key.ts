import { z } from "zod";
import { MAX_NAME_LENGTH } from "@/lib/constants";

export const developerApiKeySchema = z.object({
  id: z.string(),
  user_id: z.string(),
  workspace_id: z.string(),
  name: z.string(),
  key_prefix: z.string(),
  is_active: z.union([z.literal(0), z.literal(1)]),
  allowed_agents: z.array(z.string()).nullable(),
  request_count: z.number(),
  last_used_at: z.string().nullable(),
  expires_at: z.string().nullable(),
  created_at: z.string(),
});

export const developerApiKeyListSchema = z.array(developerApiKeySchema);

export const developerApiKeyCreatedSchema = developerApiKeySchema.extend({
  key: z.string(),
  warning: z.string(),
});

/**
 * Date is collected as YYYY-MM-DD. Empty means no expiry. A chosen date is
 * the *end* of that local day, so a key created for "today" is still usable
 * while the customer finishes configuring their integration.
 */
export const apiKeyFormSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Give the key a name so you recognise it later.")
      .max(MAX_NAME_LENGTH, `Keep the name under ${MAX_NAME_LENGTH} characters.`),
    expires_at: z.string().trim().optional().default(""),
    restrict_agents: z.boolean().default(false),
    allowed_agents: z.array(z.string()).default([]),
  })
  .superRefine((values, ctx) => {
    if (values.restrict_agents && values.allowed_agents.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["allowed_agents"],
        message: "Choose at least one agent, or allow all agents.",
      });
    }
    if (values.expires_at) {
      const parsed = Date.parse(`${values.expires_at}T23:59:59`);
      if (Number.isNaN(parsed)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["expires_at"],
          message: "Choose a valid date.",
        });
      } else if (parsed <= Date.now()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["expires_at"],
          message: "Expiry must be in the future.",
        });
      }
    }
  });

export type ApiKeyFormValues = z.infer<typeof apiKeyFormSchema>;

export const API_KEY_FORM_DEFAULTS: ApiKeyFormValues = {
  name: "",
  expires_at: "",
  restrict_agents: false,
  allowed_agents: [],
};

export function expiryToIso(value: string | undefined): string | null {
  if (!value) return null;
  return new Date(`${value}T23:59:59`).toISOString();
}
