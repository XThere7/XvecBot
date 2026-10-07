import * as React from "react";
import { cn } from "@/lib/cn";
import { RelativeTime } from "@/components/ui/relative-time";

export type ActivityItem = {
  id: string;
  kind: "document" | "agent" | "workspace" | "token";
  title: string;
  meta: string;
  createdAt: string;
  href?: string;
};

/** Recent activity, derived from the same data the stat cards already load. */
export function ActivityFeed({
  items,
  className,
}: {
  items: ActivityItem[];
  className?: string;
}) {
  if (items.length === 0) {
    return (
      <p className={cn("text-sm text-tertiary", className)}>
        Nothing has happened yet.
      </p>
    );
  }

  return (
    <ol className={cn("flex flex-col", className)}>
      {items.map((item) => (
        <li
          key={item.id}
          className="flex items-start justify-between gap-3 border-b border-subtle py-2.5 last:border-0"
        >
          <div className="min-w-0">
            <p className="truncate text-sm text-primary">{item.title}</p>
            <p className="truncate text-2xs text-tertiary">{item.meta}</p>
          </div>
          <RelativeTime date={item.createdAt} className="shrink-0 text-2xs text-tertiary" />
        </li>
      ))}
    </ol>
  );
}