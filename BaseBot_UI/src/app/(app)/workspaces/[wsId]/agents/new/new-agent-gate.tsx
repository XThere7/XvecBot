"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AgentForm } from "@/components/agents/agent-form";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/page-header";
import { workspaceHref } from "@/lib/routes";
import { useDocuments } from "@/hooks/use-documents";
import { useWorkspace } from "@/hooks/use-workspaces";

export function NewAgentGate({ wsId }: { wsId: string }) {
  const documents = useDocuments(wsId);
  const workspace = useWorkspace(wsId);
  const readyCount = (documents.data ?? []).filter((d) => d.status === "ready").length;
  const gateMet = readyCount > 0;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="New agent"
        description={`Build an assistant over the knowledge in ${
          workspace.data?.name ?? "this workspace"
        }.`}
        actions={
          <Button
            asChild
            variant="ghost"
            iconLeft={<ArrowLeft aria-hidden className="h-4 w-4" />}
          >
            <Link href={workspaceHref(wsId, "agents")}>Back to agents</Link>
          </Button>
        }
      />

      {/* Unmet prerequisite replaces the form entirely — never a disabled form. */}
      {!documents.isLoading && !gateMet ? (
        <EmptyState
          title="Train a document first"
          description="An agent with no knowledge base can't answer questions. Train at least one document, then come back."
          action={
            <Button asChild variant="primary">
              <Link href={workspaceHref(wsId, "documents")}>Go to Documents</Link>
            </Button>
          }
        />
      ) : (
        <AgentForm wsId={wsId} />
      )}
    </div>
  );
}