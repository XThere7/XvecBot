"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, apiDelete, apiGet, apiPost, apiPut } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { agentKeys } from "./use-agents";
import { embedSnippetSchema, embedTokenListSchema } from "@/schemas/token";
import type { EmbedSnippet, EmbedToken } from "@/types/api";

export function useEmbedTokens(wsId: string, agentId: string, enabled = true) {
  return useQuery({
    queryKey: agentKeys.tokens(wsId, agentId),
    queryFn: async () =>
      embedTokenListSchema.parse(
        await apiGet<EmbedToken[]>(`/workspaces/${wsId}/agents/${agentId}/tokens`),
      ),
    enabled: enabled && Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export type EmbedTokenInput = {
  label: string;
  /** `[]` clears the restriction — the backend stores null = allow any origin. */
  allowed_origins?: string[];
};

/**
 * The 201 response is the ONLY place the full token ever exists. It is handed
 * straight to the one-time modal and never persisted.
 */
export function useCreateToken(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EmbedTokenInput) =>
      apiPost<EmbedToken>(`/workspaces/${wsId}/agents/${agentId}/tokens`, {
        label: input.label,
        allowed_origins: input.allowed_origins?.length
          ? input.allowed_origins
          : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: agentKeys.tokens(wsId, agentId) });
    },
  });
}

export function useUpdateToken(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { tokenId: string } & Partial<EmbedTokenInput> & { is_active?: boolean }) => {
      const body: Record<string, unknown> = {};
      if (input.label !== undefined) body.label = input.label;
      if (input.allowed_origins !== undefined) body.allowed_origins = input.allowed_origins;
      if (input.is_active !== undefined) body.is_active = input.is_active;
      return apiPut<EmbedToken>(
        `/workspaces/${wsId}/agents/${agentId}/tokens/${input.tokenId}`,
        body,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: agentKeys.tokens(wsId, agentId) });
    },
  });
}

/** Optimistic flip for revoke / reactivate; rolled back by the refetch on error. */
export function useToggleToken(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  const key = agentKeys.tokens(wsId, agentId);

  return useMutation({
    mutationFn: (input: { tokenId: string; isActive: boolean }) =>
      apiPut<EmbedToken>(
        `/workspaces/${wsId}/agents/${agentId}/tokens/${input.tokenId}`,
        { is_active: input.isActive },
      ),
    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<EmbedToken[]>(key);
      queryClient.setQueryData<EmbedToken[]>(key, (rows) =>
        rows?.map((row) =>
          row.id === input.tokenId ? { ...row, is_active: input.isActive } : row,
        ),
      );
      return { previous };
    },
    onError: (_error, _input, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

export function useDeleteToken(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  const key = agentKeys.tokens(wsId, agentId);

  return useMutation({
    mutationFn: (tokenId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}/tokens/${tokenId}`),
    onMutate: async (tokenId) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<EmbedToken[]>(key);
      queryClient.setQueryData<EmbedToken[]>(key, (rows) =>
        rows?.filter((row) => row.id !== tokenId),
      );
      return { previous };
    },
    onError: (_error, _tokenId, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

/** The only endpoint that returns the full token after creation. */
export function useEmbedSnippet(
  wsId: string,
  agentId: string,
  tokenId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: [...agentKeys.tokens(wsId, agentId), "snippet", tokenId ?? ""],
    queryFn: async () =>
      embedSnippetSchema.parse(
        await apiGet<EmbedSnippet>(
          `/workspaces/${wsId}/agents/${agentId}/tokens/${tokenId}/snippet`,
        ),
      ),
    enabled: enabled && Boolean(wsId && agentId && tokenId),
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });
}

export function isSnippetMissing(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}