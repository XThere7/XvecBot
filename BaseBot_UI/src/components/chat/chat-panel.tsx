"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { MessageSquarePlus } from "lucide-react";
import { ChatInput } from "./chat-input";
import { ChatMessageBubble, type ChatMessage } from "./chat-message-bubble";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { STARTER_QUESTIONS } from "@/lib/reference-data";
import { chatErrorMessage, useAgentChat, useCreateConversation } from "@/hooks/use-conversations";
import { useAgent } from "@/hooks/use-agents";

/** PREMIUM MOMENT 5 — lazily loaded panel entrance. */
const BlurFade = dynamic(
  () => import("@/components/premium/blur-fade").then((m) => m.BlurFade),
  { ssr: false },
);

const WELCOME_FALLBACK = "Hi! Ask me anything about this business.";

/**
 * The docked dashboard preview. This is NOT the public widget: it shows
 * `model_used`, holds conversation state in React, and can be reset.
 */
export function ChatPanel({ wsId, agentId }: { wsId: string; agentId: string }) {
  const agentQuery = useAgent(wsId, agentId);
  const sendMessage = useAgentChat(wsId, agentId);
  const newConversation = useCreateConversation(wsId, agentId);

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [draft, setDraft] = React.useState("");
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [failedMessage, setFailedMessage] = React.useState<{
    text: string;
    message: string;
    messageId: string;
  } | null>(null);
  const logRef = React.useRef<HTMLOListElement | null>(null);

  const agent = agentQuery.data;
  // Agent.is_active is the integer 0 | 1.
  const isActive = Boolean(agent?.is_active);
  const welcome = agent?.welcome_message ?? WELCOME_FALLBACK;

  React.useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, sendMessage.isPending]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || sendMessage.isPending) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setFailedMessage(null);

    try {
      const response = await sendMessage.mutateAsync({
        message: trimmed,
        conversationId,
      });
      // Store immediately: turn 2 must reuse the same conversation.
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          modelUsed: response.model_used,
          createdAt: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      // An error never clears conversationId.
      setFailedMessage({
        text: trimmed,
        message: chatErrorMessage(error),
        messageId: userMessage.id,
      });
    }
  };

  const startNew = async () => {
    setMessages([]);
    setDraft("");
    setFailedMessage(null);
    try {
      const conversation = await newConversation.mutateAsync();
      setConversationId(conversation.id);
    } catch {
      setConversationId(null);
    }
  };

  const retryLast = () => {
    if (!failedMessage) return;
    setMessages((current) =>
      current.filter((message) => message.id !== failedMessage.messageId),
    );
    void send(failedMessage.text);
  };

  return (
    <BlurFade>
      <section
        aria-label="Agent test panel"
        className="flex h-[min(70vh,640px)] min-h-[420px] flex-col overflow-hidden rounded-md border border-subtle bg-surface shadow-elevation-1"
      >
        <header className="flex items-center justify-between gap-3 border-b border-subtle px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-base font-medium text-primary">
              {agent?.name ?? "Agent"}
            </p>
            <p className="text-2xs text-tertiary">
              Dashboard preview · answers come from this workspace&apos;s documents
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void startNew()}
            loading={newConversation.isPending}
            iconLeft={<MessageSquarePlus aria-hidden className="h-4 w-4" />}
          >
            New conversation
          </Button>
        </header>

        {!isActive && agent && (
          <div className="border-b border-subtle p-3">
            <AlertBanner tone="warning">
              This agent is inactive. Activate it to test — a live widget would
              also return 403 while it is off.
            </AlertBanner>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {agentQuery.isLoading ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton
                  key={i}
                  width={i % 2 === 0 ? "70%" : "55%"}
                  height={48}
                  className="rounded-lg"
                />
              ))}
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-5 px-2 text-center">
              <div className="max-w-md rounded-lg border border-subtle bg-surface-raised px-4 py-3 text-sm leading-5 text-primary">
                {welcome}
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {STARTER_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => setDraft(question)}
                    className="rounded-full border border-subtle bg-surface-raised px-3 py-1.5 text-xs text-secondary transition-colors hover:border-accent-500/40 hover:bg-accent-tint hover:text-accent-300"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol ref={logRef} aria-live="polite" className="flex flex-col gap-4">
              {messages.map((message) => (
                <ChatMessageBubble key={message.id} message={message} />
              ))}
              {sendMessage.isPending && (
                <ChatMessageBubble
                message={{ id: "pending", role: "assistant", content: "", isPending: true }}
              />
              )}
            </ol>
          )}
        </div>

        <footer className="border-t border-subtle p-3">
          {failedMessage && (
            <div className="mb-3">
              <ErrorPanel
                compact
                title={failedMessage.message}
                message="The message was not sent. Nothing was added to the conversation."
                onRetry={() => void retryLast()}
              />
            </div>
          )}
          <ChatInput
            value={draft}
            onChange={setDraft}
            onSend={() => void send(draft)}
            disabled={sendMessage.isPending || !isActive}
            placeholder={
              isActive
                ? "Ask a question about your documents…"
                : "Activate this agent to test it"
            }
          />
        </footer>
      </section>
    </BlurFade>
  );
}