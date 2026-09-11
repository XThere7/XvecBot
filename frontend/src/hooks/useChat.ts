/**
 * hooks/useChat.ts
 * Central chat state and streaming logic.
 * Components call this hook — they never call the API directly.
 */
import { useCallback, useRef, useState } from "react";
import { streamQuery } from "../api/client";
import type { Citation, Message, StreamEvent } from "../types";
import { nanoid } from "../utils/nanoid";

interface UseChatOptions {
  documentId?: string;
}

export function useChat({ documentId }: UseChatOptions = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const cancelRef = useRef<(() => void) | null>(null);

  const sendMessage = useCallback(
    (question: string) => {
      if (!question.trim() || isLoading) return;

      setError(null);
      setIsLoading(true);

      // Add user message
      const userMsg: Message = {
        id: nanoid(),
        role: "user",
        content: question,
        citations: [],
      };

      // Add placeholder assistant message (streaming into it)
      const assistantId = nanoid();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      cancelRef.current = streamQuery(
        {
          question,
          conversation_id: conversationIdRef.current,
          document_id: documentId,
        },
        // onToken: append each streaming token
        (token: string) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + token } : m
            )
          );
        },
        // onDone: finalise with citations and metadata
        (event: StreamEvent) => {
          if (event.conversation_id) {
            conversationIdRef.current = event.conversation_id;
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    citations: event.citations ?? [],
                    isStreaming: false,
                  }
                : m
            )
          );
          setIsLoading(false);
        },
        // onError
        (err: Error) => {
          setError(err.message);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: "An error occurred. Please try again.", isStreaming: false }
                : m
            )
          );
          setIsLoading(false);
        }
      );
    },
    [isLoading, documentId]
  );

  const cancelStream = useCallback(() => {
    cancelRef.current?.();
    setIsLoading(false);
  }, []);

  const clearChat = useCallback(() => {
    cancelRef.current?.();
    setMessages([]);
    setError(null);
    setIsLoading(false);
    conversationIdRef.current = undefined;
  }, []);

  return {
    messages,
    isLoading,
    error,
    conversationId: conversationIdRef.current,
    sendMessage,
    cancelStream,
    clearChat,
  };
}
