"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { apiGet } from "@/lib/api-client";
import { ADMIN_HOME, formatEAT } from "@/lib/admin";

type MessageRow = { message_id: string; role: string; content: string; created_at: string };
type ConversationDetail = { conversation_id: string; messages: MessageRow[]; notice: string };

export default function AdminConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = React.useState<ConversationDetail | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    apiGet<ConversationDetail>(`${ADMIN_HOME}/conversations/${params.id}/messages`, {
      skipAuthRedirect: true,
    })
      .then(setData)
      .catch(() => setError("You may lack the conversations.read permission."));
  }, [params.id]);

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!data) return <p className="text-sm text-secondary">Loading…</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-sm border border-warning-500/50 bg-surface p-4 text-sm text-warning-400">
        {data.notice}
      </div>
      <ul className="flex flex-col gap-3">
        {data.messages.map((message) => (
          <li
            key={message.message_id}
            className="rounded-sm border border-subtle bg-surface p-3 text-sm"
          >
            <p className="mb-1 text-xs text-tertiary">
              {message.role} · {formatEAT(message.created_at)}
            </p>
            <p className="whitespace-pre-wrap text-secondary">{message.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
