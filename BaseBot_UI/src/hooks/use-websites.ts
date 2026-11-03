"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, apiDelete, apiGet, apiPost } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import {
  QUERY_STALE_TIME_MS,
  WEBSITE_SYNC_POLL_INTERVAL_MS,
} from "@/lib/constants";
import { formatAbsoluteTime, formatRelativeTime } from "@/lib/format";
import {
  websitePageListSchema,
  websiteSourceListSchema,
  websiteSourceSchema,
} from "@/schemas/website";
import { workspaceKeys } from "./use-workspaces";
import type {
  WebsitePage,
  WebsiteRefreshPolicy,
  WebsiteSource,
} from "@/types/api";

export const websiteKeys = {
  list: (wsId: string) => workspaceKeys.websites(wsId),
  pages: (wsId: string, sourceId: string) =>
    workspaceKeys.websitePages(wsId, sourceId),
};

export type CreateWebsiteInput = {
  url: string;
  name?: string;
  refresh_policy: WebsiteRefreshPolicy;
};

/**
 * Sources are polled only while a crawl is running. The source row is the
 * terminal-state authority; page rows can still be appearing in parallel.
 */
export function useWebsiteSources(wsId: string | undefined) {
  return useQuery({
    queryKey: websiteKeys.list(wsId ?? ""),
    queryFn: async () =>
      websiteSourceListSchema.parse(
        await apiGet<WebsiteSource[]>(`/workspaces/${wsId}/websites`),
      ),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
    refetchInterval: (query) =>
      query.state.data?.some(
        (source) => source.status === "syncing" || source.status === "pending",
      )
        ? WEBSITE_SYNC_POLL_INTERVAL_MS
        : false,
  });
}

export function useWebsitePages(
  wsId: string | undefined,
  sourceId: string | undefined,
  options: { enabled?: boolean; poll?: boolean } = {},
) {
  const { enabled = true, poll = false } = options;

  return useQuery({
    queryKey: websiteKeys.pages(wsId ?? "", sourceId ?? ""),
    queryFn: async () =>
      websitePageListSchema.parse(
        await apiGet<WebsitePage[]>(
          `/workspaces/${wsId}/websites/${sourceId}/pages`,
        ),
      ),
    enabled: Boolean(wsId && sourceId) && enabled,
    staleTime: 10_000,
    refetchInterval: poll ? WEBSITE_SYNC_POLL_INTERVAL_MS : false,
  });
}

export function useCreateWebsiteSource(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: CreateWebsiteInput) =>
      websiteSourceSchema.parse(
        await apiPost<WebsiteSource>(`/workspaces/${wsId}/websites`, {
          url: input.url,
          name: input.name || undefined,
          refresh_policy: input.refresh_policy,
        }),
      ),
    onSuccess: (source) => {
      queryClient.setQueryData<WebsiteSource[]>(
        websiteKeys.list(wsId),
        (rows) => [source, ...(rows ?? []).filter((row) => row.id !== source.id)],
      );
      void queryClient.invalidateQueries({ queryKey: websiteKeys.list(wsId) });
    },
  });
}

export function useRefreshWebsiteSource(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sourceId: string) =>
      apiPost<{ message: string }>(
        `/workspaces/${wsId}/websites/${sourceId}/refresh`,
      ),
    onSuccess: (_data, sourceId) => {
      queryClient.setQueryData<WebsiteSource[]>(
        websiteKeys.list(wsId),
        (rows) =>
          rows?.map((row) =>
            row.id === sourceId
              ? { ...row, status: "syncing", error_message: null }
              : row,
          ),
      );
      void queryClient.invalidateQueries({ queryKey: websiteKeys.list(wsId) });
      void queryClient.invalidateQueries({
        queryKey: websiteKeys.pages(wsId, sourceId),
      });
    },
  });
}

export function useDeleteWebsiteSource(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sourceId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/websites/${sourceId}`),
    onSuccess: (_data, sourceId) => {
      queryClient.setQueryData<WebsiteSource[]>(
        websiteKeys.list(wsId),
        (rows) => rows?.filter((row) => row.id !== sourceId),
      );
      queryClient.removeQueries({
        queryKey: websiteKeys.pages(wsId, sourceId),
      });
      void queryClient.invalidateQueries({ queryKey: websiteKeys.list(wsId) });
    },
  });
}

/**
 * Website routes return owner-facing, actionable strings. Keep those visible
 * instead of collapsing every 400/409 into the generic status copy.
 */
export function websiteErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail;
    if (
      typeof detail === "string" &&
      (error.status === 400 ||
        error.status === 404 ||
        error.status === 409 ||
        error.status === 429)
    ) {
      if (error.status === 429) {
        const match = /^Next refresh available at (.+)\.$/.exec(detail);
        if (match?.[1]) {
          return `This website can be refreshed again ${formatRelativeTime(
            match[1],
          )} (${formatAbsoluteTime(match[1])}).`;
        }
      }
      return detail;
    }
    return normaliseError(error.body, error.status).message;
  }
  return "Cannot reach the server.";
}
