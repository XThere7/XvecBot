export type WorkspaceTab = "documents" | "agents" | "settings";
export type AgentTab = "overview" | "test" | "conversations" | "embed";

export const DEFAULT_WORKSPACE_TAB: WorkspaceTab = "documents";
export const DEFAULT_AGENT_TAB: AgentTab = "overview";

export function workspaceHref(
  wsId: string,
  tab: string,
  extra?: Record<string, string | undefined>,
): string {
  const params = new URLSearchParams({ tab });
  for (const [key, value] of Object.entries(extra ?? {})) {
    if (value) params.set(key, value);
  }
  return `/workspaces/${wsId}?${params.toString()}`;
}

export function agentHref(wsId: string, agentId: string, tab: string): string {
  return `/workspaces/${wsId}/agents/${agentId}?tab=${tab}`;
}

export function conversationHref(
  wsId: string,
  agentId: string,
  convId: string,
): string {
  return `/workspaces/${wsId}/agents/${agentId}/conversations/${convId}?tab=conversations`;
}

export function isWorkspaceTab(value: string | undefined): value is WorkspaceTab {
  return value === "documents" || value === "agents" || value === "settings";
}

/**
 * Where the user was before being sent to /login. Only same-origin absolute
 * paths are honoured so `?redirect=` can never bounce off-site.
 */
export function normaliseRedirectTarget(
  raw: string | null | undefined,
): string | null {
  if (!raw) return null;
  return raw.startsWith("/") && !raw.startsWith("//") ? raw : null;
}

export function isAgentTab(value: string | undefined): value is AgentTab {
  return (
    value === "overview" ||
    value === "test" ||
    value === "conversations" ||
    value === "embed"
  );
}