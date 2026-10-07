"use client";

import * as React from "react";
import Link from "next/link";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { cn } from "@/lib/cn";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { useSession } from "@/stores/session";
import type { Workspace } from "@/types/api";

export function WorkspaceSwitcher({
  current,
  collapsed = false,
}: {
  current?: Workspace | null;
  collapsed?: boolean;
}) {
  const { data: workspaces, isLoading } = useWorkspaces();
  const setActiveWorkspaceId = useSession((state) => state.setActiveWorkspaceId);
  const activeWorkspaceId = useSession((state) => state.activeWorkspaceId);

  const selected =
    current ?? workspaces?.find((w) => w.id === activeWorkspaceId) ?? workspaces?.[0] ?? null;

  React.useEffect(() => {
    if (!activeWorkspaceId && workspaces?.[0]) {
      setActiveWorkspaceId(workspaces[0].id);
    }
  }, [activeWorkspaceId, workspaces, setActiveWorkspaceId]);

  const trigger = (
    <DropdownMenuPrimitive.Trigger
      aria-label="Switch workspace"
      className={cn(
        "flex w-full items-center gap-2.5 rounded-sm border border-subtle bg-surface-raised p-2 text-left transition-colors",
        "hover:bg-surface-hover data-[state=open]:bg-surface-hover",
        collapsed && "justify-center px-0 py-2",
      )}
    >
      <span
        aria-hidden
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-accent-tint text-xs font-semibold text-accent-300"
      >
        {selected ? selected.name.slice(0, 1).toUpperCase() : "—"}
      </span>
      {!collapsed && (
        <>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-primary">
              {selected?.name ?? "No workspace"}
            </span>
            <span className="block truncate text-2xs text-tertiary">
              {isLoading ? "Loading…" : `${workspaces?.length ?? 0} workspace(s)`}
            </span>
          </span>
          <ChevronsUpDown aria-hidden className="h-3.5 w-3.5 shrink-0 text-tertiary" />
        </>
      )}
    </DropdownMenuPrimitive.Trigger>
  );

  return (
    <DropdownMenuPrimitive.Root>
      {trigger}
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="start"
          sideOffset={4}
          className="z-50 max-h-[60vh] w-[248px] overflow-y-auto rounded-md border border-subtle bg-surface-raised p-1 shadow-elevation-2"
        >
          {isLoading && (
            <div className="p-2">
              <Skeleton rows={2} height={14} />
            </div>
          )}
          {workspaces?.map((workspace) => (
            <DropdownMenuPrimitive.Item
              key={workspace.id}
              onSelect={() => setActiveWorkspaceId(workspace.id)}
              className="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-sm text-primary outline-none data-[highlighted]:bg-surface-hover"
            >
              <span className="min-w-0 flex-1 truncate">{workspace.name}</span>
              {workspace.id === selected?.id && (
                <Check aria-hidden className="h-3.5 w-3.5 text-accent-400" />
              )}
            </DropdownMenuPrimitive.Item>
          ))}
          <DropdownMenuPrimitive.Separator className="my-1 h-px bg-subtle" />
          <DropdownMenuPrimitive.Item
            asChild
            className="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-sm text-accent-300 outline-none data-[highlighted]:bg-surface-hover"
          >
            <Link href="/workspaces/new">
              <Plus aria-hidden className="h-3.5 w-3.5" />
              New workspace
            </Link>
          </DropdownMenuPrimitive.Item>
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}