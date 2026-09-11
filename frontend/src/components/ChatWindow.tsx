/**
 * components/ChatWindow.tsx
 * Scrollable list of chat messages with auto-scroll.
 */
import React, { useEffect, useRef } from "react";
import { ChatMessage } from "./ChatMessage";
import type { Message } from "../types";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

export function ChatWindow({ messages, isLoading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="chat-empty">
        <div className="chat-empty-icon">💬</div>
        <p>Select a document from the sidebar, then ask a question.</p>
        <p className="chat-empty-hint">Answers will cite the exact page numbers.</p>
      </div>
    );
  }

  return (
    <div className="chat-window" role="log" aria-live="polite" aria-label="Chat messages">
      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
