"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  API_BASE_URL,
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
} from "@/lib/api-client";
import { auth } from "@/lib/auth";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { agentKeys } from "./use-agents";
import type {
  ActionFormPayload,
  AgentAction,
  AgentActionsResponse,
  CustomForm,
  DataCollection,
  EmailDraft,
  EmailDraftListResponse,
  EmailOverview,
  EscalationListResponse,
  FormSubmission,
  LeadListResponse,
  PublicForm,
  SubmissionListResponse,
} from "@/types/api";

export const engagementKeys = {
  actions: (wsId: string, agentId: string) =>
    [...agentKeys.detail(wsId, agentId), "actions"] as const,
  actionForm: (wsId: string, agentId: string, actionId: string) =>
    [...agentKeys.detail(wsId, agentId), "actions", actionId, "form"] as const,
  leads: (wsId: string, agentId: string, search: string, status: string) =>
    [...agentKeys.detail(wsId, agentId), "leads", search, status] as const,
  collections: (wsId: string, agentId: string) =>
    [...agentKeys.detail(wsId, agentId), "collections"] as const,
  submissions: (wsId: string, agentId: string, collectionId: string) =>
    [...agentKeys.detail(wsId, agentId), "collections", collectionId, "submissions"] as const,
  forms: (wsId: string, agentId: string) =>
    [...agentKeys.detail(wsId, agentId), "forms"] as const,
  formSubmissions: (wsId: string, agentId: string, formId: string) =>
    [...agentKeys.detail(wsId, agentId), "forms", formId, "submissions"] as const,
  escalations: (wsId: string, agentId: string, status: string) =>
    [...agentKeys.detail(wsId, agentId), "escalations", status] as const,
  email: (wsId: string, agentId: string) =>
    [...agentKeys.detail(wsId, agentId), "email"] as const,
  drafts: (wsId: string, agentId: string, status: string) =>
    [...agentKeys.detail(wsId, agentId), "email", "drafts", status] as const,
  incoming: (wsId: string, agentId: string) =>
    [...agentKeys.detail(wsId, agentId), "email", "incoming"] as const,
};

// ── Actions ─────────────────────────────────────────────────────────────────

export function useAgentActions(wsId: string, agentId: string) {
  return useQuery({
    queryKey: engagementKeys.actions(wsId, agentId),
    queryFn: async () =>
      apiGet<AgentActionsResponse>(
        `/workspaces/${wsId}/agents/${agentId}/actions`,
      ),
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useUpsertAction(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      actionType: string;
      body: {
        name?: string;
        description?: string;
        instructions?: string | null;
        is_active?: boolean;
        config?: Record<string, unknown>;
      };
    }) =>
      apiPut<AgentAction>(
        `/workspaces/${wsId}/agents/${agentId}/actions/${input.actionType}`,
        input.body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.actions(wsId, agentId),
      });
    },
  });
}

export function useDeleteAction(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (actionType: string) =>
      apiDelete<void>(
        `/workspaces/${wsId}/agents/${agentId}/actions/${actionType}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.actions(wsId, agentId),
      });
    },
  });
}

export function useActionForm(
  wsId: string,
  agentId: string,
  actionId: string | null,
) {
  return useQuery({
    queryKey: engagementKeys.actionForm(wsId, agentId, actionId ?? ""),
    queryFn: async () =>
      apiGet<Omit<ActionFormPayload, "kind">>(
        `/workspaces/${wsId}/agents/${agentId}/actions/${actionId}/form`,
      ),
    enabled: Boolean(wsId && agentId && actionId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useSubmitAction(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      actionId: string;
      data: Record<string, unknown>;
      conversationId?: string | null;
    }) =>
      apiPost<{ kind: string; label: string }>(
        `/workspaces/${wsId}/agents/${agentId}/actions/${input.actionId}/submit`,
        {
          data: input.data,
          conversation_id: input.conversationId ?? undefined,
        },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId)],
      });
    },
  });
}

// ── Leads ───────────────────────────────────────────────────────────────────

export function useLeads(
  wsId: string,
  agentId: string,
  search: string,
  status: string,
) {
  return useQuery({
    queryKey: engagementKeys.leads(wsId, agentId, search, status),
    queryFn: async () => {
      const params = new URLSearchParams({ limit: "100" });
      if (search.trim()) params.set("search", search.trim());
      if (status) params.set("status", status);
      return apiGet<LeadListResponse>(
        `/workspaces/${wsId}/agents/${agentId}/leads?${params.toString()}`,
      );
    },
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useDeleteLead(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}/leads/${leadId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "leads"],
      });
    },
  });
}

// ── Data collections ────────────────────────────────────────────────────────

export function useCollections(wsId: string, agentId: string) {
  return useQuery({
    queryKey: engagementKeys.collections(wsId, agentId),
    queryFn: async () =>
      apiGet<DataCollection[]>(
        `/workspaces/${wsId}/agents/${agentId}/collections`,
      ),
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useCreateCollection(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<DataCollection>(
        `/workspaces/${wsId}/agents/${agentId}/collections`,
        body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.collections(wsId, agentId),
      });
    },
  });
}

export function useUpdateCollection(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: Record<string, unknown> }) =>
      apiPut<DataCollection>(
        `/workspaces/${wsId}/agents/${agentId}/collections/${input.id}`,
        input.body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.collections(wsId, agentId),
      });
    },
  });
}

export function useDeleteCollection(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete<void>(
        `/workspaces/${wsId}/agents/${agentId}/collections/${id}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.collections(wsId, agentId),
      });
    },
  });
}

export function useCollectionSubmissions(
  wsId: string,
  agentId: string,
  collectionId: string | null,
) {
  return useQuery({
    queryKey: engagementKeys.submissions(wsId, agentId, collectionId ?? ""),
    queryFn: async () =>
      apiGet<SubmissionListResponse>(
        `/workspaces/${wsId}/agents/${agentId}/collections/${collectionId}/submissions?limit=100`,
      ),
    enabled: Boolean(wsId && agentId && collectionId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

// ── Custom forms ────────────────────────────────────────────────────────────

export function useCustomForms(wsId: string, agentId: string) {
  return useQuery({
    queryKey: engagementKeys.forms(wsId, agentId),
    queryFn: async () =>
      apiGet<CustomForm[]>(`/workspaces/${wsId}/agents/${agentId}/forms`),
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useCreateCustomForm(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<CustomForm>(`/workspaces/${wsId}/agents/${agentId}/forms`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.forms(wsId, agentId),
      });
    },
  });
}

export function useUpdateCustomForm(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: Record<string, unknown> }) =>
      apiPut<CustomForm>(
        `/workspaces/${wsId}/agents/${agentId}/forms/${input.id}`,
        input.body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.forms(wsId, agentId),
      });
    },
  });
}

export function useDeleteCustomForm(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}/forms/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.forms(wsId, agentId),
      });
    },
  });
}

export function useFormSubmissions(
  wsId: string,
  agentId: string,
  formId: string | null,
) {
  return useQuery({
    queryKey: engagementKeys.formSubmissions(wsId, agentId, formId ?? ""),
    queryFn: async () =>
      apiGet<{ items: FormSubmission[]; total: number }>(
        `/workspaces/${wsId}/agents/${agentId}/forms/${formId}/submissions?limit=100`,
      ),
    enabled: Boolean(wsId && agentId && formId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

// ── Support escalations ─────────────────────────────────────────────────────

export function useEscalations(wsId: string, agentId: string, status: string) {
  return useQuery({
    queryKey: engagementKeys.escalations(wsId, agentId, status),
    queryFn: async () => {
      const params = new URLSearchParams({ limit: "100" });
      if (status) params.set("status", status);
      return apiGet<EscalationListResponse>(
        `/workspaces/${wsId}/agents/${agentId}/escalations?${params.toString()}`,
      );
    },
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useUpdateEscalation(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; status: "open" | "contacted" | "closed" }) =>
      apiPut(
        `/workspaces/${wsId}/agents/${agentId}/escalations/${input.id}`,
        { status: input.status },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "escalations"],
      });
    },
  });
}

// ── Email Agent ─────────────────────────────────────────────────────────────

export function useEmailOverview(wsId: string, agentId: string) {
  return useQuery({
    queryKey: engagementKeys.email(wsId, agentId),
    queryFn: async () =>
      apiGet<EmailOverview>(`/workspaces/${wsId}/agents/${agentId}/email`),
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useSaveEmailIntegration(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPut(
        `/workspaces/${wsId}/agents/${agentId}/email`,
        body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.email(wsId, agentId),
      });
    },
  });
}

export function useDeleteEmailIntegration(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}/email`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.email(wsId, agentId),
      });
    },
  });
}

export function useSimulateEmail(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<{ duplicate: boolean; draft: EmailDraft | null }>(
        `/workspaces/${wsId}/agents/${agentId}/email/simulate`,
        body,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.email(wsId, agentId),
      });
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "email", "drafts"],
      });
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.incoming(wsId, agentId),
      });
    },
  });
}

export function useEmailDrafts(wsId: string, agentId: string, status: string) {
  return useQuery({
    queryKey: engagementKeys.drafts(wsId, agentId, status),
    queryFn: async () => {
      const params = new URLSearchParams({ limit: "100" });
      if (status) params.set("status", status);
      return apiGet<EmailDraftListResponse>(
        `/workspaces/${wsId}/agents/${agentId}/email/drafts?${params.toString()}`,
      );
    },
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useUpdateEmailDraft(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: string }) =>
      apiPut<EmailDraft>(
        `/workspaces/${wsId}/agents/${agentId}/email/drafts/${input.id}`,
        { body: input.body },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "email", "drafts"],
      });
      void queryClient.invalidateQueries({
        queryKey: engagementKeys.email(wsId, agentId),
      });
    },
  });
}

export function useApproveEmailDraft(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      id: string;
      body?: string;
      confirmSimulatedSend: boolean;
    }) =>
      apiPost<EmailDraft>(
        `/workspaces/${wsId}/agents/${agentId}/email/drafts/${input.id}/approve`,
        {
          body: input.body || undefined,
          confirm_simulated_send: input.confirmSimulatedSend,
        },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "email"],
      });
    },
  });
}

export function useRejectEmailDraft(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; reason?: string }) =>
      apiPost<EmailDraft>(
        `/workspaces/${wsId}/agents/${agentId}/email/drafts/${input.id}/reject`,
        { reason: input.reason || undefined },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...agentKeys.detail(wsId, agentId), "email"],
      });
    },
  });
}

// ── CSV download ────────────────────────────────────────────────────────────

export async function downloadCsv(path: string, filename: string): Promise<void> {
  const token = auth.get();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error("Export failed");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// ── Public forms (no auth) ──────────────────────────────────────────────────

export function usePublicForm(token: string) {
  return useQuery({
    queryKey: ["public-form", token],
    queryFn: async () => apiGet<PublicForm>(`/public/forms/${token}`),
    enabled: Boolean(token),
    retry: false,
  });
}

export function useSubmitPublicForm(token: string) {
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiPost<{ id: string; status: string; message: string }>(
        `/public/forms/${token}`,
        { data },
      ),
  });
}
