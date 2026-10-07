import { WorkspaceGate } from "@/components/common/workspace-gate";
import { NewAgentGate } from "./new-agent-gate";

export const metadata = {
  title: "New agent",
};

export default async function NewAgentPage({
  params,
}: {
  params: Promise<{ wsId: string }>;
}) {
  const { wsId } = await params;

  return (
    <WorkspaceGate wsId={wsId}>
      <NewAgentGate wsId={wsId} />
    </WorkspaceGate>
  );
}