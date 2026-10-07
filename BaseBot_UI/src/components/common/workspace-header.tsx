"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { TabNav } from "@/components/common/tab-nav";
import { Button } from "@/components/ui/button";
import { RelativeTime } from "@/components/ui/relative-time";
import { Tooltip } from "@/components/ui/tooltip";
import {
  DEFAULT_WORKSPACE_TAB,
  isWorkspaceTab,
  workspaceHref,
  type WorkspaceTab,
} from "@/lib/routes";
import { useDocuments } from "@/hooks/use-documents";
import { useAgents } from "@/hooks/use-agents";
import { useWorkspace } from "@/hooks/use-workspaces";

const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: "documents", label: "Documents" },
  { id: "agents", label: "Agents" },
  { id: "settings", label: "Settings" },
];

/**
 * Workspace header + tab navigation. The active tab is in the URL (`?tab=`).
 * The "New agent" control is gated on at least one document with
 * status === "ready" — uploaded/processing/failed do not count.
 */
export function WorkspaceHeader({ wsId }: { wsId: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspace = useWorkspace(wsId);

  const tabParam = searchParams.get("tab") ?? undefined;

  // `/workspaces/[wsId]/agents` is the deep-link form of the Agents tab, so the
  // header follows the route as well as the query string.
  const currentTab: WorkspaceTab = pathname.includes("/agents")
    ? "agents"
    : isWorkspaceTab(tabParam)
      ? tabParam
      : DEFAULT_WORKSPACE_TAB;
  const documents = useDocuments(wsId);
  const agents = useAgents(wsId);

  const readyCount = (documents.data ?? []).filter((d) => d.status === "ready").length;
  const gateMet = readyCount > 0;

  const showAgentAction = currentTab === "agents" || currentTab === "documents";

  const newAgentButton = (
    <Button
      asChild={gateMet}
      variant="primary"
      disabled={!gateMet}
      iconLeft={<Plus aria-hidden className="h-4 w-4" />}
    >
      {gateMet ? (
        <Link href={`/workspaces/${wsId}/agents/new`}>New agent</Link>
      ) : (
        <span>New agent</span>
      )}
    </Button>
  );

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
            <RelativeTime date={workspace.data.created_at} className="text-xs text-tertiary" />
          ) : undefined
        }
        actions={
          showAgentAction ? (
            gateMet ? (
              newAgentButton
            ) : (
              <Tooltip
                content="Train at least one document before creating an agent — an agent with no knowledge base cannot answer."
              >
                {newAgentButton}
              </Tooltip>
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
                ? documents.data?.length
                : tab.id === "agents"
                  ? agents.data?.length
                  : undefined,
          }))}
        />
      </PageHeader>
    </div>
  );
}