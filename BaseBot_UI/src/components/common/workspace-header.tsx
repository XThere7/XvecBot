"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { TabNav } from "@/components/common/tab-nav";
import { PlanBadge } from "@/components/billing/plan-badge";
import { Button } from "@/components/ui/button";
import { RelativeTime } from "@/components/ui/relative-time";
import { Tooltip } from "@/components/ui/tooltip";
import {
  DEFAULT_WORKSPACE_TAB,
  isWorkspaceTab,
  workspaceHref,
  type WorkspaceTab,
} from "@/lib/routes";
import { useBilling } from "@/hooks/use-billing";
import { useKnowledgeReadiness } from "@/hooks/use-knowledge-readiness";
import { useAgents } from "@/hooks/use-agents";
import { useWorkspace } from "@/hooks/use-workspaces";

const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: "documents", label: "Documents" },
  { id: "agents", label: "Agents" },
  { id: "billing", label: "Plan" },
  { id: "developer", label: "Developer" },
  { id: "settings", label: "Settings" },
];

/**
 * Workspace header + tab navigation. The active tab is in the URL (`?tab=`).
 * The "New agent" control is gated on at least one ready document or indexed
 * website page — sources that are still uploading/scanning do not count.
 */
export function WorkspaceHeader({ wsId }: { wsId: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspace = useWorkspace(wsId);

  const tabParam = searchParams.get("tab") ?? undefined;

  // `/workspaces/[wsId]/agents` and `/developer` are deep-link forms of their
  // tabs, so the header follows the route as well as the query string.
  const currentTab: WorkspaceTab = pathname.includes("/agents")
    ? "agents"
    : pathname.includes("/developer")
      ? "developer"
      : isWorkspaceTab(tabParam)
        ? tabParam
        : DEFAULT_WORKSPACE_TAB;
  const knowledge = useKnowledgeReadiness(wsId);
  const agents = useAgents(wsId);
  const billing = useBilling(wsId);

  const gateMet = knowledge.hasReadyKnowledge;
  const knowledgeSourceCount =
    (knowledge.documents.data?.length ?? 0) +
    (knowledge.websites.data?.length ?? 0);

  const agentUsage = billing.data?.usage.agents;
  const atAgentLimit = agentUsage?.limit !== null && agentUsage
    ? agentUsage.used >= agentUsage.limit
    : false;
  const canCreateAgent = gateMet && !atAgentLimit;

  const showAgentAction = currentTab === "agents" || currentTab === "documents";

  const newAgentButton = (
    <Button
      asChild={canCreateAgent}
      variant="primary"
      disabled={!canCreateAgent}
      iconLeft={<Plus aria-hidden className="h-4 w-4" />}
    >
      {canCreateAgent ? (
        <Link href={`/workspaces/${wsId}/agents/new`}>New agent</Link>
      ) : (
        <span>New agent</span>
      )}
    </Button>
  );

  const agentGateMessage = !gateMet
    ? "Add at least one knowledge source before creating an agent — upload and train a document, or connect a website."
    : `You have reached the ${billing.data?.plan.name ?? "current"} plan's limit of ${
        agentUsage?.limit ?? 0
      } agents. Open Plan & usage to upgrade.`;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={workspace.data?.name ?? "Workspace"}
        description={
          workspace.data?.description ??
          "A knowledge base: documents, agents and the widgets that serve them."
        }
        meta={
          workspace.data ? (
            <div className="flex flex-wrap items-center gap-2">
              <PlanBadge plan={billing.data?.plan.id ?? workspace.data.plan} />
              {billing.data?.is_trial && (
                <span className="rounded-full border border-accent-500/40 bg-accent-tint px-2 py-0.5 text-2xs font-medium uppercase tracking-wide text-accent-300">
                  Trial
                </span>
              )}
              <RelativeTime
                date={workspace.data.created_at}
                className="text-xs text-tertiary"
              />
            </div>
          ) : undefined
        }
        actions={
          showAgentAction ? (
            canCreateAgent ? (
              newAgentButton
            ) : (
              <Tooltip content={agentGateMessage}>{newAgentButton}</Tooltip>
            )
          ) : undefined
        }
      >
        <TabNav
          active={currentTab}
          ariaLabel="Workspace sections"
          tabs={TABS.map((tab) => ({
            id: tab.id,
            label: tab.label,
            href: workspaceHref(wsId, tab.id),
            count:
              tab.id === "documents"
                ? knowledgeSourceCount
                : tab.id === "agents"
                  ? agents.data?.length
                  : undefined,
          }))}
        />
      </PageHeader>
    </div>
  );
}