import * as React from "react";
import { WorkspaceGate } from "@/components/common/workspace-gate";
import { TabContent } from "@/components/common/tab-nav";
import { DeveloperPanel } from "@/components/developer/developer-panel";

export default async function WorkspaceDeveloperPage({
  params,
}: {
  params: Promise<{ wsId: string }>;
}) {
  const { wsId } = await params;

  return (
    <WorkspaceGate wsId={wsId}>
      <TabContent tabKey="developer">
        <DeveloperPanel wsId={wsId} />
      </TabContent>
    </WorkspaceGate>
  );
}
