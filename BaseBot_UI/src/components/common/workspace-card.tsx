"use client";

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, Settings2, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { RelativeTime } from "@/components/ui/relative-time";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { workspaceHref } from "@/lib/routes";
import type { Workspace } from "@/types/api";

export type WorkspaceCardProps = {
  workspace: Workspace;
  stats?: { agents: number; readyDocuments: number; documents?: number };
  onDelete?: () => void;
  className?: string;
};

export function WorkspaceCard({
  workspace,
  stats,
  onDelete,
  className,
}: WorkspaceCardProps) {
  const router = useRouter();

  const menuItems = [
    {
      label: "Settings",
      icon: Settings2,
      onSelect: () => router.push(workspaceHref(workspace.id, "settings")),
    },
    ...(onDelete
      ? [
          {
            label: "Delete",
            icon: Trash2,
            tone: "danger" as const,
            onSelect: onDelete,
          },
        ]
      : []),
  ];

  return (
    <article
      className={cn(
        "flex flex-col rounded-md border border-subtle bg-surface p-5 shadow-elevation-1 transition-colors hover:border-strong",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <Link
          href={workspaceHref(workspace.id, "documents")}
          className="text-lg text-primary hover:text-accent-300"
        >
          <span className="line-clamp-2">{workspace.name}</span>
        </Link>
        <RowMenu items={menuItems} label={`Actions for ${workspace.name}`} />
      </div>

      <p className="mt-1.5 line-clamp-2 min-h-[40px] text-sm leading-5 text-secondary">
        {workspace.description ?? "No description"}
      </p>

      {stats && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs text-secondary">
            <FileText aria-hidden className="h-3.5 w-3.5 text-tertiary" />
            {stats.readyDocuments} ready document{stats.readyDocuments === 1 ? "" : "s"}
          </span>
          <span aria-hidden className="text-tertiary">
            ·
          </span>
          <span className="text-xs text-secondary">
            {stats.agents} agent{stats.agents === 1 ? "" : "s"}
          </span>
        </div>
      )}

      <div className="mt-auto pt-5">
        <RelativeTime
          date={workspace.created_at}
          className="inline-flex items-center gap-1.5 text-2xs text-tertiary"
        />
      </div>
    </article>
  );
}

export function WorkspaceCardSkeleton() {
  return (
    <div className="rounded-md border border-subtle bg-surface p-5 shadow-elevation-1">
      <div className="skeleton-shimmer h-4 w-1/2 rounded-sm" />
      <div className="skeleton-shimmer mt-3 h-3 w-full rounded-sm" />
      <div className="skeleton-shimmer mt-2 h-3 w-3/4 rounded-sm" />
      <div className="skeleton-shimmer mt-6 h-3 w-1/3 rounded-sm" />
    </div>
  );
}
