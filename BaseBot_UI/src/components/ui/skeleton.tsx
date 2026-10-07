import * as React from "react";
import { cn } from "@/lib/cn";

export type SkeletonVariant =
  | "text"
  | "circle"
  | "rect"
  | "card"
  | "table"
  | "code";

export type SkeletonProps = {
  variant?: SkeletonVariant;
  rows?: number;
  width?: string | number;
  height?: string | number;
  className?: string;
};

/** Placeholder content during fetch. Decorative only — `aria-hidden`. */
export function Skeleton({
  variant = "text",
  rows = 1,
  width,
  height,
  className,
}: SkeletonProps) {
  if (variant === "table") {
    return (
      <div aria-hidden className={cn("flex flex-col gap-3", className)}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="skeleton-shimmer h-4 flex-1 rounded-sm" />
            <div className="skeleton-shimmer h-4 w-24 rounded-sm" />
            <div className="skeleton-shimmer h-4 w-20 rounded-sm" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "code") {
    return (
      <div
        aria-hidden
        className={cn(
          "skeleton-shimmer rounded-lg",
          height ?? "h-[132px]",
          width ?? "w-full",
          className,
        )}
      />
    );
  }

  if (variant === "card") {
    return (
      <div
        aria-hidden
        className={cn(
          "rounded-md border border-subtle bg-surface p-6 shadow-elevation-1",
          className,
        )}
      >
        <div className="skeleton-shimmer h-4 w-1/2 rounded-sm" />
        <div className="skeleton-shimmer mt-3 h-3 w-full rounded-sm" />
        <div className="skeleton-shimmer mt-2 h-3 w-4/5 rounded-sm" />
        <div className="skeleton-shimmer mt-6 h-8 w-24 rounded-sm" />
      </div>
    );
  }

  const shape =
    variant === "circle"
      ? "rounded-full"
      : variant === "rect"
        ? "rounded-sm"
        : "rounded-sm";

  return (
    <div
      aria-hidden
      className={cn("flex flex-col gap-2", className)}
      style={rows === 1 ? undefined : { width }}
    >
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={cn("skeleton-shimmer", shape)}
          style={{
            width: rows === 1 ? width : i === rows - 1 ? "60%" : "100%",
            height: height ?? (variant === "circle" ? 40 : 14),
          }}
        />
      ))}
    </div>
  );
}

/** Wraps a loading region so assistive tech hears "busy" instead of nothing. */
export function SkeletonRegion({
  children,
  className,
  label = "Loading",
}: {
  children: React.ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <div aria-busy="true" aria-live="polite" aria-label={label} className={className}>
      {children}
    </div>
  );
}