import { AgentHeader } from "@/components/agents/agent-header";

export default async function AgentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ wsId: string; agentId: string }>;
}) {
  const { wsId, agentId } = await params;

  return (
    <div className="flex flex-col">
      <AgentHeader wsId={wsId} agentId={agentId} />
      {children}
    </div>
  );
}
