import * as React from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";

export type EmptyStateProps = {
  icon?: React.ElementType;
  /** Lucide illustration rendered large behind the icon (premium moment #6). */
  illustration?: React.ReactNode;
  title: string;
  description: React.ReactNode;
  action?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  secondaryAction?: React.ReactNode;
  size?: "sm" | "md";
  className?: string;
};

/**
 * The single "nothing here yet" composition. Every list page uses this — the
 * copy is mandated per section in frontendbot.md §9.6.
 */
export function EmptyState({
  icon: Icon,
  illustration,
  title,
  description,
  action,
  actionLabel,
  onAction,
  secondaryAction,
  size = "md",
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center overflow-hidden rounded-md border border-subtle bg-surface text-center",
        size === "md" ? "px-6 py-14" : "px-6 py-8",
        className,
      )}
    >
      {illustration && (
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-40">
          {illustration}
        </div>
      )}
      <div className="relative flex flex-col items-center">
        {Icon && (
          <div
            aria-hidden
            className={cn(
              "mb-4 flex items-center justify-center rounded-full border border-subtle bg-surface-raised text-tertiary",
              size === "md" ? "h-12 w-12" : "h-10 w-10",
            )}
          >
            <Icon className={size === "md" ? "h-6 w-6" : "h-5 w-5"} />
          </div>
        )}
        <h3 className={cn("font-semibold text-primary", size === "md" ? "text-lg" : "text-base")}>
          {title}
        </h3>
        <p className="mt-2 max-w-md text-sm leading-5 text-secondary">{description}</p>
        {(action || actionLabel) && (
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            {action ??
              (actionLabel && onAction ? (
                <Button variant="primary" onClick={onAction}>
                  {actionLabel}
                </Button>
              ) : null)}
            {secondaryAction}
          </div>
        )}
      </div>
    </div>
  );
}