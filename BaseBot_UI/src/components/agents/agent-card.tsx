"use client";

import * as React from "react";
import Link from "next/link";
import { Code2, MessageSquare, Power } from "lucide-react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RelativeTime } from "@/components/ui/relative-time";
import { ActiveBadge } from "@/components/ui/toggle";
import { modelLabel } from "@/lib/reference-data";
import { agentHref } from "@/lib/routes";
import type { Agent } from "@/types/api";

export type AgentCardProps = {
  agent: Agent;
  wsId: string;
  onToggleActive?: (next: boolean) => void;
  toggling?: boolean;
  compact?: boolean;
  className?: string;
};

export function AgentCard({
  agent,
  wsId,
  onToggleActive,
  toggling = false,
  compact = false,
  className,
}: AgentCardProps) {
  // Agent.is_active arrives as the integer 0 | 1 — always normalise.
  const isActive = Boolean(agent.is_active);

  return (
    <article
      className={cn(
        "flex flex-col rounded-md border border-subtle bg-surface p-5 shadow-elevation-1 transition-colors",
        "hover:border-strong",
        !isActive && "opacity-80",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={agentHref(wsId, agent.id, "overview")}
            className="text-lg text-primary hover:text-accent-300"
          >
            <span className="line-clamp-2">{agent.name}</span>
          </Link>
          <p className="mt-1.5 line-clamp-2 text-sm leading-5 text-secondary">
            {agent.description ?? "No description"}
          </p>
        </div>
        {onToggleActive && (
          <Button
            variant="ghost"
            size="sm"
            loading={toggling}
            aria-label={isActive ? `Deactivate ${agent.name}` : `Activate ${agent.name}`}
            iconLeft={!toggling && <Power aria-hidden className="h-4 w-4" />}
            onClick={() => onToggleActive(!isActive)}
            className="shrink-0"
          >
            {isActive ? "On" : "Off"}
          </Button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <ActiveBadge active={isActive} />
        <Badge tone="neutral">{agent.language}</Badge>
        <Badge tone="neutral" title={agent.model}>
          {modelLabel(agent.model)}
        </Badge>
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-5">
        <RelativeTime
          date={agent.created_at}
          className="text-2xs text-tertiary"
        />
        {!compact && (
          <div className="flex items-center gap-1.5">
            <Button
              asChild
              variant="secondary"
              size="sm"
              iconLeft={<MessageSquare aria-hidden className="h-4 w-4" />}
            >
              <Link href={agentHref(wsId, agent.id, "test")}>Test</Link>
            </Button>
            <Button
              asChild
              variant="secondary"
              size="sm"
              iconLeft={<Code2 aria-hidden className="h-4 w-4" />}
            >
              <Link href={agentHref(wsId, agent.id, "embed")}>Embed</Link>
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}