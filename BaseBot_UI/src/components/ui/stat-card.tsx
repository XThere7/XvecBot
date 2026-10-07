import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { Skeleton } from "./skeleton";

export type StatCardProps = {
  label: string;
  value: React.ReactNode;
  icon?: React.ElementType;
  hint?: string;
  loading?: boolean;
  href?: string;
  tone?: "default" | "accent";
  className?: string;
};

const TONE_ICON: Record<string, string> = {
  default: "text-tertiary",
  accent: "text-accent-400",
};

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  loading,
  href,
  tone = "default",
  className,
}: StatCardProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium text-tertiary">{label}</p>
        {Icon && <Icon aria-hidden className={cn("h-4 w-4 shrink-0", TONE_ICON[tone])} />}
      </div>
      <div className="mt-3">
        {loading ? (
          <Skeleton width={64} height={28} />
        ) : (
          <p className="text-2xl text-primary">{value}</p>
        )}
      </div>
      {hint && <p className="mt-1 text-2xs text-tertiary">{hint}</p>}
    </>
  );

  const classes = cn(
    "block rounded-md border border-subtle bg-surface p-5 shadow-elevation-1",
    href && "transition-colors duration-150 hover:border-strong hover:bg-surface-raised",
    className,
  );

  if (href) {
    return (
      <Link href={href} className={classes}>
        {body}
      </Link>
    );
  }

  return <div className={classes}>{body}</div>;
}