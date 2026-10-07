import * as React from "react";
import { WorkspaceGate } from "@/components/common/workspace-gate";
import { TabContent } from "@/components/common/tab-nav";
import { AgentsPanel } from "@/components/agents/agents-panel";

export default async function WorkspaceAgentsPage({
  params,
}: {
  params: Promise<{ wsId: string }>;
}) {
  const { wsId } = await params;

  return (
    <WorkspaceGate wsId={wsId}>
      <TabContent tabKey="agents">
        <AgentsPanel wsId={wsId} />
      </TabContent>
    </WorkspaceGate>
  );
}
