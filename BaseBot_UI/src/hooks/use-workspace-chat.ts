"use client";

import { useMutation } from "@tanstack/react-query";
import { ApiRequestError, apiPost } from "@/lib/api-client";
import { workspaceChatResponseSchema } from "@/schemas/chat";
import type { WorkspaceChatResponse } from "@/types/api";

/**
 * Workspace-level Q&A: `POST /workspaces/{ws}/chat`.
 *
 * This is the endpoint to use for any workspace question. The legacy
 * `/api/v1/query` route is broken (a LangGraph state-key collision in Phase 1)
 * and is API-key authenticated, so no UI is built against it.
 *
 * There is no `conversation_id` on this route — the caller manages the history
 * it sends back, which is why the current dashboard surfaces (documents, agents,
 * test preview) do not use it.
 */
export function useWorkspaceChat(wsId: string) {
  return useMutation({
    mutationFn: async (input: {
      message: string;
      conversationHistory?: { role: "user" | "assistant"; content: string }[];
    }): Promise<WorkspaceChatResponse> => {
      const body: Record<string, unknown> = { message: input.message };
      if (input.conversationHistory && input.conversationHistory.length > 0) {
        body.conversation_history = input.conversationHistory;
      }
      const response = await apiPost<WorkspaceChatResponse>(
        `/workspaces/${wsId}/chat`,
        body,
      );
      return workspaceChatResponseSchema.parse(response);
    },
  });
}

export function workspaceChatErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 422) return "That question could not be sent.";
    if (error.status === 0) return "Cannot reach the server.";
  }
  return "Something went wrong. Please try again.";
}