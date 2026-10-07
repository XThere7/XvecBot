"use client";

import * as React from "react";
import { CornerDownLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MESSAGE_COUNTER_WARN, MAX_MESSAGE_LENGTH } from "@/lib/constants";
import { cn } from "@/lib/cn";

export type ChatInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  autoFocus?: boolean;
  className?: string;
};

/** Enter sends, Shift+Enter inserts a newline. The counter appears at 80%. */
export function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
  placeholder = "Ask a question about your documents…",
  maxLength = MAX_MESSAGE_LENGTH,
  className,
}: ChatInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const length = value.length;
  const showCounter = length >= maxLength * 0.8;
  const overLimit = length >= maxLength;

  const submit = () => {
    if (disabled || !value.trim()) return;
    onSend();
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        className={cn(
          "flex items-end gap-2 rounded-md border bg-inset p-2 transition-colors",
          disabled
            ? "border-subtle opacity-60"
            : "border-strong focus-within:border-accent-500 focus-within:outline-2 focus-within:outline-offset-0 focus-within:outline-accent-500",
        )}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          disabled={disabled}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => {
            onChange(event.target.value);
            const node = event.target;
            node.style.height = "auto";
            node.style.height = `${Math.min(node.scrollHeight, 160)}px`;
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent px-1 py-1 text-base leading-5 text-primary placeholder:text-tertiary focus:outline-none disabled:cursor-not-allowed"
        />
        <Button
          type="button"
          size="sm"
          variant="primary"
          onClick={submit}
          disabled={disabled || !value.trim()}
          iconLeft={<CornerDownLeft aria-hidden className="h-3.5 w-3.5" />}
        >
          Send
        </Button>
      </div>

      <div className="flex items-center justify-between gap-3">
        <span className="text-2xs text-tertiary">
          Enter to send · Shift + Enter for a new line
        </span>
        {showCounter && (
          <span
            aria-live="polite"
            className={cn(
              "font-mono text-2xs",
              overLimit
                ? "text-danger-400"
                : length >= MESSAGE_COUNTER_WARN
                  ? "text-warning-400"
                  : "text-tertiary",
            )}
          >
            {length}/{maxLength}
          </span>
        )}
      </div>
    </div>
  );
}