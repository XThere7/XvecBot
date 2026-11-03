"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, api, apiDelete, apiGet, apiPost } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import {
  MEDIA_SYNC_POLL_INTERVAL_MS,
  QUERY_STALE_TIME_MS,
} from "@/lib/constants";
import {
  socialMediaCreateResponseSchema,
  socialMediaListResponseSchema,
  socialMediaSourceSchema,
  socialMediaSyncResponseSchema,
} from "@/schemas/media";
import { workspaceKeys } from "./use-workspaces";
import type {
  SocialMediaCreateResponse,
  SocialMediaListResponse,
  SocialMediaSource,
  SocialMediaSyncResponse,
} from "@/types/api";

export const mediaKeys = {
  list: (wsId: string, agentId: string) =>
    workspaceKeys.media(wsId, agentId),
};

const ACTIVE_STATUSES = new Set(["pending", "extracting", "indexing"]);

export function useMediaSources(wsId: string, agentId: string) {
  return useQuery({
    queryKey: mediaKeys.list(wsId, agentId),
    queryFn: async () =>
      socialMediaListResponseSchema.parse(
        await apiGet<SocialMediaListResponse>(
          `/workspaces/${wsId}/agents/${agentId}/media`,
        ),
      ),
    staleTime: QUERY_STALE_TIME_MS,
    refetchInterval: (query) =>
      query.state.data?.sources.some((source) =>
        ACTIVE_STATUSES.has(source.status),
      )
        ? MEDIA_SYNC_POLL_INTERVAL_MS
        : false,
  });
}

export function useCreateMediaSource(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (url: string) =>
      socialMediaCreateResponseSchema.parse(
        await apiPost<SocialMediaCreateResponse>(
          `/workspaces/${wsId}/agents/${agentId}/media`,
          { url },
        ),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: mediaKeys.list(wsId, agentId),
      });
    },
  });
}

export function useUpdateMediaSource(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      sourceId: string;
      content_text: string;
      title?: string;
    }) =>
      socialMediaSourceSchema.parse(
        await api<SocialMediaSource>(
          `/workspaces/${wsId}/agents/${agentId}/media/${input.sourceId}`,
          {
            method: "PATCH",
            body: {
              content_text: input.content_text,
              title: input.title || undefined,
            },
          },
        ),
      ),
    onSuccess: (source) => {
      queryClient.setQueryData<SocialMediaListResponse>(
        mediaKeys.list(wsId, agentId),
        (current) =>
          current
            ? {
                ...current,
                sources: current.sources.map((row) =>
                  row.id === source.id ? source : row,
                ),
              }
            : current,
      );
      void queryClient.invalidateQueries({
        queryKey: mediaKeys.list(wsId, agentId),
      });
    },
  });
}

export function useRetryMediaSource(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceId: string) =>
      socialMediaSourceSchema.parse(
        await apiPost<SocialMediaSource>(
          `/workspaces/${wsId}/agents/${agentId}/media/${sourceId}/retry`,
        ),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: mediaKeys.list(wsId, agentId),
      });
    },
  });
}

export function useSyncMediaSources(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceIds?: string[]) =>
      socialMediaSyncResponseSchema.parse(
        await apiPost<SocialMediaSyncResponse>(
          `/workspaces/${wsId}/agents/${agentId}/media/sync`,
          sourceIds ? { source_ids: sourceIds } : {},
        ),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: mediaKeys.list(wsId, agentId),
      });
    },
  });
}

export function useDeleteMediaSource(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) =>
      apiDelete<void>(
        `/workspaces/${wsId}/agents/${agentId}/media/${sourceId}`,
      ),
    onSuccess: (_data, sourceId) => {
      queryClient.setQueryData<SocialMediaListResponse>(
        mediaKeys.list(wsId, agentId),
        (current) =>
          current
            ? {
                ...current,
                sources: current.sources.filter((row) => row.id !== sourceId),
                usage: {
                  ...current.usage,
                  used: Math.max(0, current.usage.used - 1),
                },
              }
            : current,
      );
      void queryClient.invalidateQueries({
        queryKey: mediaKeys.list(wsId, agentId),
      });
    },
  });
}

export function mediaDuplicateSourceId(error: unknown): string | null {
  if (!(error instanceof ApiRequestError)) return null;
  const detail = (error.body as { detail?: unknown } | null)?.detail;
  if (
    error.status === 409 &&
    detail &&
    typeof detail === "object" &&
    "code" in detail &&
    (detail as { code?: unknown }).code === "duplicate_media" &&
    "existing_source_id" in detail
  ) {
    return String((detail as { existing_source_id?: unknown }).existing_source_id);
  }
  return null;
}

export function mediaErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    return normaliseError(error.body, error.status).message;
  }
  return "Cannot reach the server.";
}
