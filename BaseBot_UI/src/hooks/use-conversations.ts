"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, apiDelete, apiGet, apiPost } from "@/lib/api-client";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { agentKeys } from "./use-agents";
import {
  agentChatResponseSchema,
  conversationListSchema,
  conversationThreadSchema,
} from "@/schemas/chat";
import type { AgentChatResponse, Conversation, ConversationThread } from "@/types/api";

export function useConversations(wsId: string, agentId: string, enabled = true) {
  return useQuery({
    queryKey: agentKeys.conversations(wsId, agentId),
    queryFn: async () =>
      conversationListSchema.parse(
        await apiGet<Conversation[]>(
          `/workspaces/${wsId}/agents/${agentId}/conversations`,
        ),
      ),
    enabled: enabled && Boolean(wsId && agentId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useConversationThread(
  wsId: string,
  agentId: string,
  convId: string | undefined,
) {
  return useQuery({
    queryKey: [...agentKeys.conversations(wsId, agentId), "thread", convId ?? ""],
    queryFn: async () =>
      conversationThreadSchema.parse(
        await apiGet<ConversationThread>(
          `/workspaces/${wsId}/agents/${agentId}/conversations/${convId}`,
        ),
      ),
    enabled: Boolean(wsId && agentId && convId),
    staleTime: QUERY_STALE_TIME_MS,
  });
}

export function useDeleteConversation(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (convId: string) =>
      apiDelete<void>(`/workspaces/${wsId}/agents/${agentId}/conversations/${convId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentKeys.conversations(wsId, agentId),
      });
    },
  });
}

/** Returns 201, not 200. */
export function useCreateConversation(wsId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<Conversation>(
        `/workspaces/${wsId}/agents/${agentId}/conversations/new`,
      ),
    onSuccess: (conversation) => {
      queryClient.setQueryData(
        agentKeys.conversations(wsId, agentId),
        (rows: Conversation[] | undefined) => [conversation, ...(rows ?? [])],
      );
    },
  });
}

/**
 * Turn 1 omits `conversation_id`; later turns pass it back. `conversation_id`
 * is stored immediately on success and never cleared by an error.
 */
export function useAgentChat(wsId: string, agentId: string) {
  return useMutation({
    mutationFn: async (input: {
      message: string;
      conversationId: string | null;
    }): Promise<AgentChatResponse> => {
      const body: Record<string, unknown> = { message: input.message };
      if (input.conversationId) body.conversation_id = input.conversationId;

      const response = await apiPost<AgentChatResponse>(
        `/workspaces/${wsId}/agents/${agentId}/chat`,
        body,
      );
      return agentChatResponseSchema.parse(response);
    },
  });
}

export function chatErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 403) return "This agent is inactive. Activate it to test.";
    if (error.status === 429) return "You're sending messages too fast.";
    if (error.status === 422) return "That message could not be sent.";
    if (error.status === 0) return "Cannot reach the server.";
  }
  return "Something went wrong. Please try again.";
}