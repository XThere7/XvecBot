"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Trash2 } from "lucide-react";
import { ChatMessageBubble, type ChatMessage } from "@/components/chat/chat-message-bubble";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { NotFoundPanel } from "@/components/common/not-found-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import { agentHref } from "@/lib/routes";
import { useAgent } from "@/hooks/use-agents";
import { useConversationThread, useDeleteConversation } from "@/hooks/use-conversations";

export function ConversationThreadView({
  wsId,
  agentId,
  convId,
}: {
  wsId: string;
  agentId: string;
  convId: string;
}) {
  const router = useRouter();
  const threadQuery = useConversationThread(wsId, agentId, convId);
  const agentQuery = useAgent(wsId, agentId);
  const remove = useDeleteConversation(wsId, agentId);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const thread = threadQuery.data;

  const messages: ChatMessage[] = React.useMemo(
    () =>
      (thread?.messages ?? []).map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        sources: message.sources,
        createdAt: message.created_at,
      })),
    [thread],
  );

  const confirmDelete = async () => {
    try {
      await remove.mutateAsync(convId);
      toast.success({ title: "Conversation deleted" });
      router.push(agentHref(wsId, agentId, "conversations"));
    } catch {
      toast.error({ title: "Could not delete the conversation" });
    }
  };

  if (threadQuery.isError) {
    const status = (threadQuery.error as { status?: number })?.status;
    if (status === 404) {
      return (
        <NotFoundPanel
          title="Conversation not found"
          description="This conversation was deleted, or it belongs to another agent."
          backHref={agentHref(wsId, agentId, "conversations")}
          backLabel="Back to conversations"
        />
      );
    }
    return (
      <ErrorPanel
        title="We could not load this conversation"
        statusCode={status}
        onRetry={() => void threadQuery.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          asChild
          variant="ghost"
          size="sm"
          iconLeft={<ArrowLeft aria-hidden className="h-4 w-4" />}
        >
          <Link href={agentHref(wsId, agentId, "conversations")}>
            All conversations
          </Link>
        </Button>
        <Button
          variant="dangerGhost"
          size="sm"
          iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
          onClick={() => setConfirmOpen(true)}
        >
          Delete conversation
        </Button>
      </div>

      <AlertBanner tone="info" title="Read-only preview">
        This is a preview of a stored conversation. To continue chatting, open
        the Test tab.
      </AlertBanner>

      {threadQuery.isLoading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton
              key={i}
              width={i % 2 === 0 ? "60%" : "75%"}
              height={44}
              className="rounded-lg"
            />
          ))}
        </div>
      ) : messages.length === 0 ? (
        <EmptyState
          size="sm"
          title="This conversation has no messages yet"
          description="It was created but never used. Send the first message from the Test tab."
          action={
            <Button asChild variant="primary">
              <Link href={agentHref(wsId, agentId, "test")}>Open the Test tab</Link>
            </Button>
          }
        />
      ) : (
        <ol aria-live="polite" className="flex flex-col gap-4">
          {messages.map((message) => (
            <ChatMessageBubble key={message.id} message={message} readOnly />
          ))}
        </ol>
      )}

      <ConfirmationDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Delete conversation?"
        body={
          <p>
            This permanently deletes this conversation with{" "}
            <strong className="font-medium text-primary">
              {agentQuery.data?.name ?? "this agent"}
            </strong>
            .
          </p>
        }
        confirmLabel="Delete conversation"
        confirmLoading={remove.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}