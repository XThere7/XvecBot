"use client";

import * as React from "react";
import { NotFoundPanel } from "@/components/common/not-found-panel";
import { ErrorPanel } from "@/components/common/error-panel";
import { isNotFound } from "@/hooks/use-workspaces";
import { useWorkspace } from "@/hooks/use-workspaces";

/**
 * Renders a dedicated not-found state for a missing workspace instead of a
 * generic error block, and keeps every panel behind the same gate.
 */
export function WorkspaceGate({
  wsId,
  children,
}: {
  wsId: string;
  children: React.ReactNode;
}) {
  const workspace = useWorkspace(wsId);

  if (workspace.isError) {
    if (isNotFound(workspace.error)) {
      return (
        <NotFoundPanel
          title="Workspace not found"
          description="This workspace no longer exists, or it belongs to another account."
          backHref="/workspaces"
          backLabel="Back to workspaces"
        />
      );
    }
    return (
      <ErrorPanel
        title="We could not load this workspace"
        statusCode={(workspace.error as { status?: number })?.status}
        onRetry={() => void workspace.refetch()}
      />
    );
  }

  return <>{children}</>;
}