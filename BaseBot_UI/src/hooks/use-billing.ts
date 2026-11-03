"use client";

import { useQuery } from "@tanstack/react-query";
import { ApiRequestError, apiGet } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { workspaceKeys } from "./use-workspaces";
import { billingSummarySchema, plansResponseSchema } from "@/schemas/billing";
import type {
  BillingSummary,
  PlanLimitDetail,
  PlansResponse,
} from "@/types/api";

export const billingKeys = {
  plans: ["billing", "plans"] as const,
  workspace: (wsId: string) =>
    [...workspaceKeys.detail(wsId), "billing"] as const,
};

/** The public plan catalogue — used by the pricing page and billing panel. */
export function usePlans() {
  return useQuery({
    queryKey: billingKeys.plans,
    queryFn: async () =>
      plansResponseSchema.parse(
        await apiGet<PlansResponse>("/billing/plans"),
      ),
    staleTime: 5 * 60 * 1000,
  });
}

/** Current plan, live usage and the UTC monthly reset date for a workspace. */
export function useBilling(wsId: string | undefined) {
  return useQuery({
    queryKey: billingKeys.workspace(wsId ?? ""),
    queryFn: async () =>
      billingSummarySchema.parse(
        await apiGet<BillingSummary>(`/workspaces/${wsId}/billing`),
      ),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

/**
 * Extract the structured plan-limit detail from a 402/403/429. Every limit
 * gate uses this shape, so one helper drives the agent/storage/chat prompts.
 */
export function planLimitFromError(error: unknown): PlanLimitDetail | null {
  if (
    !(error instanceof ApiRequestError) ||
    ![402, 403, 429].includes(error.status)
  ) {
    return null;
  }

  const detail = (error.body as { detail?: unknown } | null)?.detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) {
    return null;
  }

  const value = detail as Record<string, unknown>;
  if (typeof value.message !== "string") return null;

  return {
    code:
      value.code === "plan_feature_locked"
        ? "plan_feature_locked"
        : "plan_limit_reached",
    resource: typeof value.resource === "string" ? value.resource : "plan",
    message: value.message,
    plan: typeof value.plan === "string" ? value.plan : "free",
    plan_name:
      typeof value.plan_name === "string" ? value.plan_name : undefined,
    used:
      typeof value.used === "number" || typeof value.used === "string"
        ? value.used
        : null,
    limit:
      typeof value.limit === "number" || typeof value.limit === "string"
        ? value.limit
        : null,
    resets_at:
      typeof value.resets_at === "string" ? value.resets_at : null,
    upgrade_required: Boolean(value.upgrade_required),
    payments_configured: Boolean(value.payments_configured),
  };
}
