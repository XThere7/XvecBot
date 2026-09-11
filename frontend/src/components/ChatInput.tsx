/**
 * components/ChatInput.tsx
 * Message input box with send / stop controls.
 */
import React, { useCallback, useRef, useState } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  isLoading: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onCancel, isLoading, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  }, [value, isLoading, onSend]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    [submit]
  );

  return (
    <div className="chat-input-bar">
      <textarea
        ref={textareaRef}
        className="chat-textarea"
        rows={2}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask a question about your document… (Enter to send, Shift+Enter for newline)"
        disabled={disabled || isLoading}
        aria-label="Question input"
      />
      <div className="chat-input-actions">
        {isLoading ? (
          <button className="btn btn-stop" onClick={onCancel} aria-label="Stop generation">
            ⏹ Stop
          </button>
        ) : (
          <button
            className="btn btn-send"
            onClick={submit}
            disabled={!value.trim() || !!disabled}
            aria-label="Send message"
          >
            Send ↵
          </button>
        )}
      </div>
    </div>
  );
}
