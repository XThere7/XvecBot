import * as React from "react";
import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "info" | "warning" | "success" | "danger" | "accent";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "border-subtle bg-surface-raised text-secondary",
  info: "border-info-500/30 bg-info-500/10 text-info-400",
  warning: "border-warning-500/30 bg-warning-500/10 text-warning-400",
  success: "border-success-500/30 bg-success-500/10 text-success-400",
  danger: "border-danger-500/30 bg-danger-500/10 text-danger-400",
  accent: "border-accent-500/30 bg-accent-tint text-accent-300",
};

const DOT_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-neutral-500",
  info: "bg-info-500",
  warning: "bg-warning-500",
  success: "bg-success-500",
  danger: "bg-danger-500",
  accent: "bg-accent-500",
};

export type BadgeProps = {
  tone?: BadgeTone;
  size?: "sm" | "md";
  dot?: boolean;
  animated?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title?: string;
};

export function Badge({
  tone = "neutral",
  size = "sm",
  dot = false,
  animated = false,
  icon,
  children,
  className,
  title,
}: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-chip border font-medium",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            DOT_CLASSES[tone],
            animated && "animate-pulse-dot",
          )}
        />
      )}
      {icon}
      {children}
    </span>
  );
}