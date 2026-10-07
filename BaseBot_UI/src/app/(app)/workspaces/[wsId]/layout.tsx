import { WorkspaceHeader } from "@/components/common/workspace-header";

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ wsId: string }>;
}) {
  const { wsId } = await params;

  return (
    <div className="flex flex-col">
      <WorkspaceHeader wsId={wsId} />
      {children}
    </div>
  );
}
