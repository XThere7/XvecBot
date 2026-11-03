import { z } from "zod";

export const planIdSchema = z.enum(["free", "standard", "pro"]);

const unlimitedCount = z.number().nullable();

export const planLimitsSchema = z.object({
  agents: unlimitedCount,
  documents: unlimitedCount,
  pages_indexed: unlimitedCount,
  website_sources: unlimitedCount,
  website_refresh: z.enum(["manual", "weekly", "daily"]),
  api_keys: unlimitedCount,
  chat_messages: unlimitedCount,
  embed_tokens: unlimitedCount,
  storage_bytes: z.number(),
  members: z.number(),
  social_media_sources: z.number(),
});

export const planFeaturesSchema = z.object({
  website_widget: z.boolean(),
  citations: z.boolean(),
  conversation_history: z.boolean(),
  lead_forms: z.boolean(),
  email_integration: z.boolean(),
  lead_qualification: z.boolean(),
  actions: z.boolean(),
  analytics: z.enum(["usage", "basic", "advanced"]),
  whatsapp: z.boolean(),
  developer_api: z.boolean(),
  automations: z.boolean(),
  custom_branding: z.boolean(),
  support: z.enum(["community", "standard", "priority"]),
});

export const planSchema = z.object({
  id: planIdSchema,
  name: z.string(),
  tagline: z.string(),
  price_tzs: z.number(),
  price_label: z.string(),
  price_display: z.string(),
  period: z.enum(["forever", "month"]),
  recommended: z.boolean(),
  limits: planLimitsSchema,
  features: planFeaturesSchema,
  coming_soon: z.array(z.string()),
});

export const plansResponseSchema = z.object({
  plans: z.array(planSchema),
  currency: z.string(),
  trial: z.object({
    duration_days: z.number(),
    description: z.string(),
    limits: planLimitsSchema,
  }),
  payments_configured: z.boolean(),
  upgrade_available: z.boolean(),
  launch_note: z.string(),
});

const usageCounterSchema = z.object({
  used: z.number(),
  limit: z.number().nullable(),
  percent: z.number(),
  unlimited: z.boolean(),
});

export const billingSummarySchema = z.object({
  workspace_id: z.string(),
  plan: planSchema,
  plans: z.array(planSchema),
  is_trial: z.boolean(),
  base_plan: planIdSchema,
  effective_plan: z.union([planIdSchema, z.literal("trial")]),
  trial_ends_at: z.string().nullable(),
  days_remaining: z.number().nullable(),
  usage: z.object({
    agents: usageCounterSchema,
    documents: usageCounterSchema,
    pages_indexed: usageCounterSchema,
    website_sources: usageCounterSchema,
    api_keys: usageCounterSchema,
    embed_tokens: usageCounterSchema,
    chat_messages: usageCounterSchema.extend({
      period_start: z.string(),
      period_end: z.string(),
      resets_at: z.string(),
    }),
    storage: z.object({
      used_bytes: z.number(),
      limit_bytes: z.number(),
      percent: z.number(),
    }),
    members: usageCounterSchema.extend({
      enforced: z.boolean(),
    }),
  }),
  period: z.object({
    start: z.string(),
    end: z.string(),
    resets_at: z.string(),
  }),
  plan_started_at: z.string().nullable(),
  payments_configured: z.boolean(),
  upgrade_available: z.boolean(),
  launch_note: z.string(),
});

/** Tolerant parse for a plan-limit body — never throws on an unexpected shape. */
export const planLimitDetailSchema = z.object({
  code: z.string(),
  resource: z.string(),
  message: z.string(),
  plan: z.string(),
  plan_name: z.string().optional(),
  used: z.union([z.number(), z.string()]).nullable().optional(),
  limit: z.union([z.number(), z.string()]).nullable().optional(),
  resets_at: z.string().nullable().optional(),
  upgrade_required: z.boolean().optional(),
  payments_configured: z.boolean().optional(),
});
