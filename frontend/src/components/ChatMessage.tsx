/**
 * components/ChatMessage.tsx
 * A single chat bubble with inline citation chips.
 */
import React from "react";
import type { Message } from "../types";

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-role">{isUser ? "You" : "Assistant"}</div>
      <div className="message-bubble">
        <div className="message-content">
          {message.content}
          {message.isStreaming && <span className="cursor-blink">▍</span>}
        </div>

        {/* Citation chips */}
        {!message.isStreaming && message.citations.length > 0 && (
          <div className="citations" aria-label="Sources">
            <span className="citations-label">Sources:</span>
            {message.citations.map((cite) => (
              <span
                key={cite.chunk_id}
                className="citation-chip"
                title={cite.text_preview}
                aria-label={`Page ${cite.page}`}
              >
                p.{cite.page}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
