"use client";

import * as React from "react";
import Link from "next/link";
import { Eye, Trash2 } from "lucide-react";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { RelativeTime } from "@/components/ui/relative-time";
import { SearchInput } from "@/components/ui/search-input";
import { toast } from "@/lib/toast";
import { agentHref, conversationHref } from "@/lib/routes";
import { useAgent } from "@/hooks/use-agents";
import { useConversations, useDeleteConversation } from "@/hooks/use-conversations";
import type { Conversation } from "@/types/api";

export function ConversationsPanel({ wsId, agentId }: { wsId: string; agentId: string }) {
  const agentQuery = useAgent(wsId, agentId);
  const conversationsQuery = useConversations(wsId, agentId);
  const remove = useDeleteConversation(wsId, agentId);

  const [search, setSearch] = React.useState("");
  const [pendingDelete, setPendingDelete] = React.useState<Conversation | null>(null);

  const agentName = agentQuery.data?.name ?? "this agent";

  // Fixed ordering: most recently updated first. No sort control, no paginator.
  const rows = React.useMemo(() => {
    const all = conversationsQuery.data ?? [];
    const needle = search.trim().toLowerCase();
    const filtered = needle
      ? all.filter((conversation) =>
          (conversation.title ?? "").toLowerCase().includes(needle),
        )
      : all;
    return [...filtered].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
  }, [conversationsQuery.data, search]);

  const columns: DataTableColumn<Conversation>[] = [
    {
      id: "title",
      header: "Conversation",
      primary: true,
      cell: (conversation) => (
        <Link
          href={conversationHref(wsId, agentId, conversation.id)}
          className="text-base text-primary hover:text-accent-300"
        >
          {/* "New Conversation" until the backend titles it from turn 1. */}
          <span className="line-clamp-1">{conversation.title ?? "New Conversation"}</span>
        </Link>
      ),
    },
    {
      id: "updated_at",
      header: "Updated",
      cell: (conversation) => (
        <RelativeTime
          date={conversation.updated_at}
          live
          className="text-sm text-secondary"
        />
      ),
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (conversation) => (
        <div className="flex items-center justify-end gap-1">
          <Button
            asChild
            variant="ghost"
            size="sm"
            iconLeft={<Eye aria-hidden className="h-4 w-4" />}
          >
            <Link href={conversationHref(wsId, agentId, conversation.id)}>Open</Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Delete ${conversation.title ?? "conversation"}`}
            iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
            onClick={() => setPendingDelete(conversation)}
          />
        </div>
      ),
    },
  ];

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove.mutateAsync(pendingDelete.id);
      toast.success({ title: "Conversation deleted" });
      setPendingDelete(null);
    } catch {
      toast.error({ title: "Could not delete the conversation" });
    }
  };

  if (conversationsQuery.isError) {
    return (
      <ErrorPanel
        title="We could not load conversations"
        statusCode={(conversationsQuery.error as { status?: number })?.status}
        onRetry={() => void conversationsQuery.refetch()}
      />
    );
  }

  const all = conversationsQuery.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      {all.length > 3 && (
        <SearchInput
          label="Search conversations"
          placeholder="Search conversations…"
          value={search}
          onChange={setSearch}
        />
      )}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(conversation) => conversation.id}
        loading={conversationsQuery.isLoading}
        skeletonRows={5}
        emptyState={
          all.length === 0 ? (
            <EmptyState
              title="No conversations yet"
              description="Once your widget is live, visitor conversations appear here."
              action={
                <Button asChild variant="primary">
                  <Link href={agentHref(wsId, agentId, "test")}>
                    Start a conversation
                  </Link>
                </Button>
              }
            />
          ) : (
            <EmptyState
              size="sm"
              title="No matches"
              description={`Nothing matched “${search}”.`}
              action={
                <Button variant="secondary" onClick={() => setSearch("")}>
                  Clear search
                </Button>
              }
            />
          )
        }
      />

      <ConfirmationDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete conversation?"
        body={
          <p>
            This permanently deletes this conversation with{" "}
            <strong className="font-medium text-primary">{agentName}</strong>.
          </p>
        }
        confirmLabel="Delete conversation"
        confirmLoading={remove.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}