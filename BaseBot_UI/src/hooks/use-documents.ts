"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, apiDelete, apiGet, apiPost } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { workspaceKeys } from "./use-workspaces";
import {
  documentStatusSchema,
  trainResponseSchema,
  workspaceDocumentListSchema,
} from "@/schemas/document";
import type { DocStatus, WorkspaceDocument } from "@/types/api";

export const documentKeys = {
  list: (wsId: string) => workspaceKeys.documents(wsId),
};

export function useDocuments(wsId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.list(wsId ?? ""),
    queryFn: async () =>
      workspaceDocumentListSchema.parse(
        await apiGet<WorkspaceDocument[]>(`/workspaces/${wsId}/documents`),
      ),
    enabled: Boolean(wsId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export type UploadResult = {
  document: WorkspaceDocument;
  /** 202 = start polling, 200 = already ready, 409 = a run is already in flight. */
  train: "poll" | "ready" | "conflict" | "skipped";
};

export function useUploadDocument(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File): Promise<UploadResult> => {
      const form = new FormData();
      form.append("file", file);

      const document = await apiPost<WorkspaceDocument>(
        `/workspaces/${wsId}/documents`,
        form,
      );

      // Auto-train immediately after a successful upload: the user asked to
      // add knowledge, so make it searchable without a second click.
      try {
        const response = await apiPost(`/workspaces/${wsId}/documents/${document.id}/train`);
        const parsed = trainResponseSchema.parse(response);
        return { document, train: parsed.status === "processing" ? "poll" : "ready" };
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 409) {
          return { document, train: "conflict" };
        }
        if (error instanceof ApiRequestError) {
          // The upload succeeded; training failed. The row carries the status.
          return { document, train: "skipped" };
        }
        throw error;
      }
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(wsId) });
      void queryClient.invalidateQueries({ queryKey: workspaceKeys.agents(wsId) });
      if (result.train === "conflict") {
        // Another run is in flight — the existing poll loop picks it up.
        return;
      }
    },
  });
}

/** Patches one row in the cached list without a full refetch. */
export function usePatchDocumentStatus(wsId: string) {
  const queryClient = useQueryClient();
  return React.useCallback(
    (docId: string, patch: Partial<WorkspaceDocument>) => {
      queryClient.setQueryData<WorkspaceDocument[]>(
        documentKeys.list(wsId),
        (rows) => rows?.map((row) => (row.id === docId ? { ...row, ...patch } : row)),
      );
    },
    [queryClient, wsId],
  );
}

export function useTrainDocument(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (docId: string) => {
      const response = await apiPost(`/workspaces/${wsId}/documents/${docId}/train`);
      return { docId, ...trainResponseSchema.parse(response) };
    },
    onSuccess: (result) => {
      queryClient.setQueryData<WorkspaceDocument[]>(
        documentKeys.list(wsId),
        (rows) =>
          rows?.map((row) =>
            row.id === result.docId
              ? {
                  ...row,
                  status: (result.status === "processing" ? "processing" : "ready") as DocStatus,
                }
              : row,
          ),
      );
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(wsId) });
      void queryClient.invalidateQueries({ queryKey: workspaceKeys.agents(wsId) });
    },
  });
}

export function useDocumentStatus(wsId: string, docId: string) {
  return useQuery({
    queryKey: [...documentKeys.list(wsId), "status", docId],
    queryFn: async () =>
      documentStatusSchema.parse(
        await apiGet(`/workspaces/${wsId}/documents/${docId}/status`),
      ),
    enabled: Boolean(wsId && docId),
    staleTime: 0,
    refetchInterval: false,
  });
}

export function useDeleteDocument(wsId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (docId: string) => apiDelete<void>(`/workspaces/${wsId}/documents/${docId}`),
    onSuccess: (_data, docId) => {
      queryClient.setQueryData<WorkspaceDocument[]>(
        documentKeys.list(wsId),
        (rows) => rows?.filter((row) => row.id !== docId),
      );
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(wsId) });
      void queryClient.invalidateQueries({ queryKey: workspaceKeys.agents(wsId) });
    },
  });
}

export function describeDocumentError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return normaliseError(error.body, error.status).message;
  }
  return "Cannot reach the server.";
}