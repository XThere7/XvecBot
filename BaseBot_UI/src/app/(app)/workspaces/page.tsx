"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FolderOpen, Plus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { WorkspaceCard, WorkspaceCardSkeleton } from "@/components/common/workspace-card";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { SearchInput } from "@/components/ui/search-input";
import { useDeleteWorkspace, useWorkspaces } from "@/hooks/use-workspaces";
import { toast } from "@/lib/toast";
import type { Workspace } from "@/types/api";

export default function WorkspacesPage() {
  const router = useRouter();
  const query = useWorkspaces();
  const deleteWorkspace = useDeleteWorkspace();
  const [search, setSearch] = React.useState("");
  const [pendingDelete, setPendingDelete] = React.useState<Workspace | null>(null);

  const workspaces = query.data ?? [];
  const filtered = workspaces.filter((workspace) => {
    if (!search.trim()) return true;
    const needle = search.trim().toLowerCase();
    return (
      workspace.name.toLowerCase().includes(needle) ||
      (workspace.description ?? "").toLowerCase().includes(needle)
    );
  });

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteWorkspace.mutateAsync(pendingDelete.id);
      toast.success({ title: "Workspace deleted" });
      setPendingDelete(null);
      router.push("/workspaces");
    } catch {
      // The mutation surfaces through the dialog's own error handling.
      toast.error({
        title: "Could not delete the workspace",
        description: "Check your connection and try again.",
      });
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Workspaces"
        description="Each workspace is a knowledge base: its documents, the agents built from them, and the widgets that serve them."
        actions={
          <Button asChild variant="primary" iconLeft={<Plus aria-hidden className="h-4 w-4" />}>
            <Link href="/workspaces/new">New workspace</Link>
          </Button>
        }
      />

      {query.isError ? (
        <ErrorPanel
          title="We could not load your workspaces"
          statusCode={(query.error as { status?: number })?.status}
          onRetry={() => void query.refetch()}
        />
      ) : workspaces.length === 0 && query.isSuccess ? (
        <EmptyState
          icon={FolderOpen}
          title="No workspaces yet"
          description="A workspace holds your documents and the agents built from them. Start with one."
          actionLabel="Create workspace"
          onAction={() => router.push("/workspaces/new")}
        />
      ) : (
        <>
          {workspaces.length > 3 && (
            <SearchInput
              label="Search workspaces"
              placeholder="Search workspaces…"
              value={search}
              onChange={setSearch}
            />
          )}

          {query.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <WorkspaceCardSkeleton key={i} />
              ))}
            </div>
          ) : filtered.length === 0 ? (
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
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((workspace) => (
                <WorkspaceCard
                  key={workspace.id}
                  workspace={workspace}
                  onDelete={() => setPendingDelete(workspace)}
                />
              ))}
            </div>
          )}
        </>
      )}

      <ConfirmationDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete workspace?"
        body={
          pendingDelete ? (
            <p>
              This permanently deletes{" "}
              <strong className="font-medium text-primary">{pendingDelete.name}</strong>{" "}
              — every document, chunk and embedding, all agents, all
              conversations and all embed tokens. This cannot be undone.
            </p>
          ) : null
        }
        confirmLabel="Delete workspace"
        confirmLoading={deleteWorkspace.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}