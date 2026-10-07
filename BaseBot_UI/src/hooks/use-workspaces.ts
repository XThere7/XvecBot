"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, apiDelete, apiGet, apiPost, apiPut } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { toast } from "@/lib/toast";
import { workspaceListSchema, workspaceSchemaApi } from "@/schemas/workspace";
import type { Workspace } from "@/types/api";

export const workspaceKeys = {
  all: ["workspaces"] as const,
  list: () => ["workspaces", "list"] as const,
  detail: (id: string) => ["workspaces", "detail", id] as const,
  documents: (id: string) => ["workspaces", "detail", id, "documents"] as const,
  agents: (id: string) => ["workspaces", "detail", id, "agents"] as const,
};

export function useWorkspaces() {
  return useQuery({
    queryKey: workspaceKeys.list(),
    queryFn: async () => workspaceListSchema.parse(await apiGet<Workspace[]>("/workspaces")),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useWorkspace(wsId: string | undefined) {
  return useQuery({
    queryKey: workspaceKeys.detail(wsId ?? ""),
    queryFn: async () =>
      workspaceSchemaApi.parse(await apiGet<Workspace>(`/workspaces/${wsId}`)),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export type WorkspaceInput = {
  name: string;
  description?: string | null;
  system_prompt?: string | null;
};

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: WorkspaceInput) =>
      apiPost<Workspace>("/workspaces", {
        name: input.name,
        description: input.description || null,
        system_prompt: input.system_prompt || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all });
      toast.success({ title: "Workspace created" });
    },
  });
}

/** PUT ignores nulls, so only genuinely changed fields are sent. */
export function useUpdateWorkspace(wsId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<WorkspaceInput>) => {
      const body: Record<string, unknown> = {};
      if (input.name !== undefined) body.name = input.name;
      if (input.description !== undefined) body.description = input.description || null;
      if (input.system_prompt !== undefined) {
        body.system_prompt = input.system_prompt || null;
      }
      return apiPut<Workspace>(`/workspaces/${wsId}`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all });
      void queryClient.invalidateQueries({ queryKey: workspaceKeys.detail(wsId) });
    },
  });
}

export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (wsId: string) => apiDelete<void>(`/workspaces/${wsId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all });
    },
  });
}

/** 404 helpers shared by every detail page. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}

export function errorStatus(error: unknown): number | undefined {
  return error instanceof ApiRequestError ? error.status : undefined;
}