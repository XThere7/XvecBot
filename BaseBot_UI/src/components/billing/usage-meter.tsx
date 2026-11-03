import * as React from "react";
import { cn } from "@/lib/cn";

export type UsageMeterProps = {
  label: string;
  used: number;
  /** null means unlimited. */
  limit: number | null;
  percent: number;
  /** "count" → "3 of 5"; "bytes" → "1.2 MB of 1.0 GB". */
  format?: "count" | "bytes";
  hint?: React.ReactNode;
  className?: string;
};

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-GB").format(value);
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const kb = value / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function UsageMeter({
  label,
  used,
  limit,
  percent,
  format = "count",
  hint,
  className,
}: UsageMeterProps) {
  const unlimited = limit === null;
  const clamped = unlimited ? 0 : Math.max(0, Math.min(100, percent));
  const tone =
    clamped >= 100
      ? "bg-danger-500"
      : clamped >= 80
        ? "bg-warning-500"
        : "bg-accent-500";
  const value =
    format === "bytes"
      ? `${formatBytes(used)} of ${formatBytes(limit ?? 0)}`
      : unlimited
        ? `${formatCount(used)} used · Unlimited`
        : `${formatCount(used)} of ${formatCount(limit ?? 0)}`;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-primary">{label}</p>
        <p className="text-xs tabular-nums text-tertiary">{value}</p>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={unlimited ? undefined : (limit ?? 0)}
        aria-valuenow={unlimited ? undefined : Math.min(used, limit ?? 0)}
        aria-valuetext={`${value} used`}
        className="h-1.5 w-full overflow-hidden rounded-full bg-inset"
      >
        {!unlimited && (
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300",
              tone,
            )}
            style={{ width: `${clamped}%` }}
          />
        )}
      </div>
      {hint && <div className="text-2xs leading-4 text-tertiary">{hint}</div>}
    </div>
  );
}
