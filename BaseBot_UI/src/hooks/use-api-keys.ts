"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { workspaceKeys } from "./use-workspaces";
import {
  developerApiKeyCreatedSchema,
  developerApiKeyListSchema,
} from "@/schemas/api-key";
import type { DeveloperApiKey, DeveloperApiKeyCreated } from "@/types/api";

export const apiKeyKeys = {
  list: (wsId: string) =>
    [...workspaceKeys.detail(wsId), "api-keys"] as const,
  detail: (wsId: string, keyId: string) =>
    [...workspaceKeys.detail(wsId), "api-keys", keyId] as const,
};

export function useApiKeys(wsId: string) {
  return useQuery({
    queryKey: apiKeyKeys.list(wsId),
    queryFn: async () =>
      developerApiKeyListSchema.parse(
        await apiGet<DeveloperApiKey[]>(`/workspaces/${wsId}/api-keys`),
      ),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export type CreateApiKeyInput = {
  name: string;
  allowed_agents: string[] | null;
  expires_at: string | null;
};

export function useCreateApiKey(wsId: string) {
  const queryClient = useQueryClient();
  const key = apiKeyKeys.list(wsId);

  return useMutation({
    mutationFn: async (input: CreateApiKeyInput) =>
      developerApiKeyCreatedSchema.parse(
        await apiPost<DeveloperApiKeyCreated>(`/workspaces/${wsId}/api-keys`, input),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

export type UpdateApiKeyInput = {
  keyId: string;
  name?: string;
  /** null clears the restriction; omitted leaves it unchanged. */
  allowed_agents?: string[] | null;
  is_active?: 0 | 1;
};

export function useUpdateApiKey(wsId: string) {
  const queryClient = useQueryClient();
  const key = apiKeyKeys.list(wsId);

  return useMutation({
    mutationFn: async ({ keyId, ...body }: UpdateApiKeyInput) =>
      apiPut<DeveloperApiKey>(`/workspaces/${wsId}/api-keys/${keyId}`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

export function useDeleteApiKey(wsId: string) {
  const queryClient = useQueryClient();
  const key = apiKeyKeys.list(wsId);

  return useMutation({
    mutationFn: (keyId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/api-keys/${keyId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
