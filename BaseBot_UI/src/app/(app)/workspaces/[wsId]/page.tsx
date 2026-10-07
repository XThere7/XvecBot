import { DocumentsPanel } from "@/components/documents/documents-panel";
import { AgentsPanel } from "@/components/agents/agents-panel";
import { WorkspaceSettingsPanel } from "@/components/workspaces/workspace-settings-panel";
import { WorkspaceGate } from "@/components/common/workspace-gate";
import { TabContent } from "@/components/common/tab-nav";

/**
 * `/workspaces/[wsId]` renders the tab selected by `?tab=`. The tab lives in the
 * URL so links are shareable and browser Back works. `/workspaces/[wsId]/agents`
 * is the deep-link form of the Agents tab and renders the same panel.
 */
export default async function WorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ wsId: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { wsId } = await params;
  const query = await searchParams;
  const tab = typeof query.tab === "string" ? query.tab : "documents";

  return (
    <WorkspaceGate wsId={wsId}>
      <TabContent tabKey={tab}>
        {tab === "agents" ? (
          <AgentsPanel wsId={wsId} />
        ) : tab === "settings" ? (
          <WorkspaceSettingsPanel wsId={wsId} />
        ) : (
          <DocumentsPanel wsId={wsId} />
        )}
      </TabContent>
    </WorkspaceGate>
  );
}