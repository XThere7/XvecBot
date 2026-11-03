"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AgentForm } from "@/components/agents/agent-form";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { workspaceHref } from "@/lib/routes";
import { useBilling } from "@/hooks/use-billing";
import { useKnowledgeReadiness } from "@/hooks/use-knowledge-readiness";
import { useWorkspace } from "@/hooks/use-workspaces";

export function NewAgentGate({ wsId }: { wsId: string }) {
  const knowledge = useKnowledgeReadiness(wsId);
  const workspace = useWorkspace(wsId);
  const billing = useBilling(wsId);
  const gateMet = knowledge.hasReadyKnowledge;
  const agentUsage = billing.data?.usage.agents;
  const atAgentLimit = agentUsage?.limit !== null && agentUsage
    ? agentUsage.used >= agentUsage.limit
    : false;

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
      {knowledge.isLoading ? (
        <Skeleton variant="card" />
      ) : !gateMet ? (
        <EmptyState
          title="Add knowledge first"
          description="An agent with no knowledge base can't answer questions. Upload and train a document, or connect a website, then come back."
          action={
            <Button asChild variant="primary">
              <Link href={workspaceHref(wsId, "documents")}>Go to Documents</Link>
            </Button>
          }
        />
      ) : atAgentLimit && agentUsage ? (
        <EmptyState
          title="Agent limit reached"
          description={`The ${
            billing.data?.plan.name ?? "current"
          } plan includes ${agentUsage.limit} agent${
            agentUsage.limit === 1 ? "" : "s"
          } and you have used ${agentUsage.used}. Delete an agent or upgrade to add another.`}
          action={
            <Button asChild variant="primary">
              <Link href={workspaceHref(wsId, "billing")}>
                View plan &amp; usage
              </Link>
            </Button>
          }
          secondaryAction={
            <Button asChild variant="secondary">
              <Link href={workspaceHref(wsId, "agents")}>Back to agents</Link>
            </Button>
          }
        />
      ) : (
        <AgentForm wsId={wsId} />
      )}
    </div>
  );
}