"use client";

import * as React from "react";
import { Bot, ExternalLink, MessageSquarePlus, RotateCw, ShieldAlert } from "lucide-react";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessageBubble, type ChatMessage } from "@/components/chat/chat-message-bubble";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { APP_NAME } from "@/lib/constants";
import { STARTER_QUESTIONS } from "@/lib/reference-data";
import { getPublicAgent, PublicApiError, sendPublicChat } from "@/lib/public-api";
import type { PublicAgentInfo } from "@/types/api";

function newMessageId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function AgentAvatar({
  agent,
  size = "md",
}: {
  agent: PublicAgentInfo | null;
  size?: "md" | "lg";
}) {
  const dimension = size === "lg" ? "h-14 w-14" : "h-10 w-10";
  if (agent?.icon_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- icon hosts are dynamic
      <img
        src={agent.icon_url}
        alt=""
        className={`${dimension} shrink-0 rounded-full border border-subtle object-cover`}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`${dimension} flex shrink-0 items-center justify-center rounded-full border border-accent-500/30 bg-accent-tint text-accent-300`}
    >
      <Bot className={size === "lg" ? "h-6 w-6" : "h-5 w-5"} />
    </span>
  );
}

export function HostedChat({ token }: { token: string }) {
  const [agent, setAgent] = React.useState<PublicAgentInfo | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [fatal, setFatal] = React.useState<string | null>(null);
  const [infoAttempt, setInfoAttempt] = React.useState(0);

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);
  const [chatError, setChatError] = React.useState<string | null>(null);
  const [failedText, setFailedText] = React.useState<string | null>(null);
  const [chatDisabled, setChatDisabled] = React.useState(false);

  const bottomRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFatal(null);
    getPublicAgent(token, controller.signal)
      .then((info) => {
        if (!controller.signal.aborted) setAgent(info);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setFatal(
          error instanceof PublicApiError
            ? error.message
            : "This chat is temporarily unavailable. Please try again.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, infoAttempt]);

  React.useEffect(() => {
    if (!agent) return;
    document.title = `${agent.name} · ${APP_NAME}`;
  }, [agent]);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  const sendMessage = async (text: string, appendUser: boolean) => {
    const trimmed = text.trim();
    if (!agent || !trimmed || sending || chatDisabled) return;

    if (appendUser) {
      setMessages((previous) => [
        ...previous,
        {
          id: newMessageId(),
          role: "user",
          content: trimmed,
        },
      ]);
      setInput("");
    }
    setSending(true);
    setChatError(null);

    try {
      const data = await sendPublicChat(token, trimmed, conversationId);
      setConversationId(data.conversation_id);
      setFailedText(null);
      setMessages((previous) => [
        ...previous,
        {
          id: newMessageId(),
          role: "assistant",
          content: data.answer,
          sources: data.sources,
        },
      ]);
    } catch (error) {
      const message =
        error instanceof PublicApiError
          ? error.message
          : "Something went wrong. Please try again.";
      setChatError(message);
      setFailedText(trimmed);
      if (
        error instanceof PublicApiError &&
        (error.status === 401 || error.status === 403 || error.status === 404)
      ) {
        setChatDisabled(true);
      }
    } finally {
      setSending(false);
    }
  };

  const resetChat = () => {
    setMessages([]);
    setConversationId(null);
    setInput("");
    setChatError(null);
    setFailedText(null);
  };

  if (loading) {
    return (
      <div className="flex min-h-dvh flex-col bg-canvas">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 px-4 py-8">
          <Skeleton variant="card" height={84} />
          <Skeleton variant="card" height={160} />
          <Skeleton variant="card" height={96} />
        </div>
      </div>
    );
  }

  if (fatal || !agent) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-canvas px-5">
        <div className="w-full max-w-md rounded-lg border border-subtle bg-surface p-6 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-danger-500/30 bg-danger-500/10 text-danger-400">
            <ShieldAlert aria-hidden className="h-6 w-6" />
          </span>
          <h1 className="mt-4 text-lg text-primary">Chat unavailable</h1>
          <p className="mt-2 text-sm leading-5 text-secondary">
            {fatal ?? "This chat link is invalid, expired, or has been disabled."}
          </p>
          <Button
            variant="secondary"
            className="mt-5"
            iconLeft={<RotateCw aria-hidden className="h-4 w-4" />}
            onClick={() => setInfoAttempt((n) => n + 1)}
          >
            Try again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="sticky top-0 z-20 border-b border-subtle bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-3 px-4 py-3">
          <AgentAvatar agent={agent} />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-medium text-primary">{agent.name}</h1>
            <p className="mt-0.5 flex items-center gap-1.5 text-2xs text-tertiary">
              <span
                aria-hidden
                className={`h-1.5 w-1.5 rounded-full ${
                  chatDisabled ? "bg-neutral-500" : "bg-success-500"
                }`}
              />
              {chatDisabled ? "Unavailable" : `AI assistant · ${agent.language}`}
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            iconLeft={<MessageSquarePlus aria-hidden className="h-4 w-4" />}
            onClick={resetChat}
            disabled={messages.length === 0 && !conversationId}
          >
            New chat
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
        <div className="flex-1 py-6">
          {messages.length === 0 ? (
            <section className="rounded-lg border border-subtle bg-surface p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <AgentAvatar agent={agent} size="lg" />
                <div className="min-w-0">
                  <h2 className="text-lg text-primary">
                    {agent.name}
                  </h2>
                  {agent.description && (
                    <p className="mt-1 text-sm leading-5 text-secondary">
                      {agent.description}
                    </p>
                  )}
                  <p className="mt-3 text-base leading-6 text-primary">
                    {agent.welcome_message}
                  </p>
                </div>
              </div>

              <div className="mt-5 grid gap-2">
                <p className="text-2xs font-medium uppercase tracking-wide text-tertiary">
                  Try asking
                </p>
                {STARTER_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => void sendMessage(question, true)}
                    className="rounded-md border border-subtle bg-inset px-3 py-2.5 text-left text-sm text-secondary transition-colors hover:border-strong hover:text-primary"
                  >
                    {question}
                  </button>
                ))}
              </div>

              <p className="mt-4 flex items-center gap-1.5 text-2xs text-tertiary">
                <ExternalLink aria-hidden className="h-3 w-3" />
                Answers are based on the business&apos;s uploaded documents.
              </p>
            </section>
          ) : (
            <ul
              aria-label="Conversation"
              aria-live="polite"
              className="flex flex-col gap-5"
            >
              {messages.map((message) => (
                <ChatMessageBubble key={message.id} message={message} />
              ))}
              {sending && (
                <li className="flex w-full gap-3">
                  <span
                    aria-hidden
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-subtle bg-surface-raised text-tertiary"
                  >
                    <Bot className="h-3.5 w-3.5" />
                  </span>
                  <TypingIndicator label={`${agent.name} is typing`} />
                </li>
              )}
            </ul>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="sticky bottom-0 z-10 -mx-4 border-t border-subtle bg-canvas/95 px-4 py-3 backdrop-blur">
          {chatError && (
            <AlertBanner
              tone="danger"
              title="Message not sent"
              className="mb-3"
              action={
                failedText && !chatDisabled ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void sendMessage(failedText, false)}
                  >
                    Retry
                  </Button>
                ) : undefined
              }
            >
              {chatError}
            </AlertBanner>
          )}

          {chatDisabled ? (
            <div className="rounded-md border border-subtle bg-surface px-4 py-3 text-sm text-tertiary">
              This conversation is no longer available. Ask the business for a new
              chat link.
            </div>
          ) : (
            <>
              <ChatInput
                value={input}
                onChange={(value) => {
                  setInput(value);
                  if (chatError) setChatError(null);
                }}
                onSend={() => void sendMessage(input, true)}
                disabled={sending}
                placeholder={`Message ${agent.name}…`}
                autoFocus
              />
              <p className="mt-1.5 text-center text-2xs text-tertiary">
                AI can make mistakes. Check important information.
              </p>
            </>
          )}
        </div>
      </main>

      <footer className="border-t border-subtle px-4 py-3 text-center text-2xs text-tertiary">
        Powered by {APP_NAME}
      </footer>
    </div>
  );
}
