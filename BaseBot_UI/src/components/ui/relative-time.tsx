import * as React from "react";
import { cn } from "@/lib/cn";
import { formatAbsoluteTime, formatRelativeTime, parseApiDate } from "@/lib/format";

export type RelativeTimeProps = {
  date: string | null | undefined;
  /** Re-render on an interval so "2 minutes ago" stays honest. */
  live?: boolean;
  className?: string;
};

/** "3 minutes ago" with the absolute UTC timestamp in the title. */
export function RelativeTime({ date, live = false, className }: RelativeTimeProps) {
  const [, force] = React.useReducer((n: number) => n + 1, 0);

  React.useEffect(() => {
    if (!live) return;
    const id = setInterval(force, 30_000);
    return () => clearInterval(id);
  }, [live]);

  const parsed = parseApiDate(date);
  if (!parsed) return <span className={cn("text-tertiary", className)}>—</span>;

  return (
    <time
      dateTime={parsed.toISOString()}
      title={formatAbsoluteTime(date)}
      className={className}
    >
      {formatRelativeTime(date)}
    </time>
  );
}