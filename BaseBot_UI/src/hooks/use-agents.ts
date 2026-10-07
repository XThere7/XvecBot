"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { workspaceKeys } from "./use-workspaces";
import { agentListSchema, agentSchemaApi } from "@/schemas/agent";
import type { Agent } from "@/types/api";

export const agentKeys = {
  list: (wsId: string) => workspaceKeys.agents(wsId),
  detail: (wsId: string, agentId: string) =>
    [...workspaceKeys.agents(wsId), "detail", agentId] as const,
  conversations: (wsId: string, agentId: string) =>
    [...workspaceKeys.agents(wsId), "detail", agentId, "conversations"] as const,
  tokens: (wsId: string, agentId: string) =>
    [...workspaceKeys.agents(wsId), "detail", agentId, "tokens"] as const,
};

export function useAgents(wsId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.list(wsId ?? ""),
    queryFn: async () =>
      agentListSchema.parse(await apiGet<Agent[]>(`/workspaces/${wsId}/agents`)),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useAgent(wsId: string | undefined, agentId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.detail(wsId ?? "", agentId ?? ""),
    queryFn: async () =>
      agentSchemaApi.parse(
        await apiGet<Agent>(`/workspaces/${wsId}/agents/${agentId}`),
      ),
    enabled: Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export type AgentInput = {
  name?: string;
  description?: string | null;
  system_prompt?: string | null;
  welcome_message?: string | null;
  model?: string;
  temperature?: number;
  language?: string;
  is_active?: 0 | 1;
};

export function useCreateAgent(wsId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AgentInput) =>
      apiPost<Agent>(`/workspaces/${wsId}/agents`, {
        name: input.name,
        description: input.description || null,
        system_prompt: input.system_prompt,
        welcome_message: input.welcome_message || null,
        model: input.model,
        temperature: input.temperature,
        language: input.language,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: agentKeys.list(wsId) });
    },
  });
}

/**
 * PUT ignores null values, so only fields that actually changed are sent.
 * `welcome_message` is reset with a single space — the public API treats a
 * blank value as "use the default greeting".
 */
export function useUpdateAgent(wsId: string, agentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: AgentInput) => {
      const body: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(input)) {
        if (value === undefined) continue;
        body[key] = value;
      }
      return apiPut<Agent>(`/workspaces/${wsId}/agents/${agentId}`, body);
    },
    onSuccess: (agent) => {
      queryClient.setQueryData(
        agentKeys.detail(wsId, agentId),
        agentSchemaApi.parse(agent),
      );
      void queryClient.invalidateQueries({ queryKey: agentKeys.list(wsId) });
    },
  });
}

export function useToggleAgentActive(wsId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { agentId: string; isActive: boolean }) =>
      apiPut<Agent>(`/workspaces/${wsId}/agents/${input.agentId}`, {
        is_active: input.isActive ? 1 : 0,
      }),
    onSuccess: (agent) => {
      queryClient.setQueryData(
        agentKeys.detail(wsId, agent.id),
        agentSchemaApi.parse(agent),
      );
      void queryClient.invalidateQueries({ queryKey: agentKeys.list(wsId) });
    },
  });
}

export function useDeleteAgent(wsId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}`),
    onSuccess: (_data, agentId) => {
      queryClient.removeQueries({ queryKey: agentKeys.detail(wsId, agentId) });
      void queryClient.invalidateQueries({ queryKey: agentKeys.list(wsId) });
    },
  });
}