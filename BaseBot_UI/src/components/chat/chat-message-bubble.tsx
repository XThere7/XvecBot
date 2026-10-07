"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { Bot, RotateCw, User } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { RelativeTime } from "@/components/ui/relative-time";
import { SourceChips } from "./source-chips";
import { TypingIndicator } from "./typing-indicator";
import type { Source } from "@/types/api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "error";
  content: string;
  sources?: Source[] | null;
  createdAt?: string;
  modelUsed?: string;
  isPending?: boolean;
};

export type ChatMessageBubbleProps = {
  message: ChatMessage;
  readOnly?: boolean;
  onRetry?: () => void;
};

/**
 * One message. Content is always rendered as plain text with pre-wrap —
 * LLM output and filenames are untrusted, so never dangerouslySetInnerHTML.
 */
export function ChatMessageBubble({
  message,
  readOnly = false,
  onRetry,
}: ChatMessageBubbleProps) {
  const reduceMotion = useReducedMotion();
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const ungrounded =
    message.role === "assistant" && (message.sources?.length ?? 0) === 0;

  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      aria-label={
        isUser
          ? "You"
          : isError
            ? "Error"
            : `Assistant${message.createdAt ? `, ${message.createdAt}` : ""}`
      }
      className={cn(
        "flex w-full gap-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <span
          aria-hidden
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
            isError
              ? "border-danger-500/40 bg-danger-500/10 text-danger-400"
              : "border-subtle bg-surface-raised text-tertiary",
          )}
        >
          {isError ? <RotateCw className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </span>
      )}

      <div className={cn("flex min-w-0 max-w-[min(680px,88%)] flex-col gap-2", isUser && "items-end")}>
        {message.isPending ? (
          <TypingIndicator />
        ) : (
          <div
            className={cn(
              "rounded-lg px-3.5 py-2.5 text-base leading-5",
              "whitespace-pre-wrap break-words",
              isUser && "rounded-br-chip bg-accent-500 text-inverse",
              !isUser && !isError && "rounded-bl-chip border border-subtle bg-surface text-primary",
              isError &&
                "rounded-bl-chip border border-danger-500/40 bg-danger-500/10 text-danger-400",
              ungrounded && "border-l-2 border-l-warning-500",
            )}
          >
            {message.content}
          </div>
        )}

        {message.role === "assistant" && !message.isPending && (
          <>
            <SourceChips sources={message.sources} />
            <div className="flex flex-wrap items-center gap-3">
              {/* model_used is shown here and nowhere else — never in the widget. */}
              {message.modelUsed && (
                <span className="font-mono text-2xs text-tertiary">
                  {message.modelUsed}
                </span>
              )}
              {message.createdAt && (
                <RelativeTime date={message.createdAt} className="text-2xs text-tertiary" />
              )}
              {!readOnly && (
                <CopyButton
                  value={message.content}
                  label="Copy answer"
                  variant="ghost"
                  className="h-6 px-1.5 text-2xs"
                />
              )}
            </div>
          </>
        )}

        {isError && onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>

      {isUser && (
        <span
          aria-hidden
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-subtle bg-surface-raised text-tertiary"
        >
          <User className="h-3.5 w-3.5" />
        </span>
      )}
    </motion.li>
  );
}
