"use client";

import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "@/lib/cn";

export type ToggleProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
  size?: "sm" | "md";
  /** Visually hidden accessible name. */
  label: string;
  className?: string;
  id?: string;
};

/**
 * Boolean switch. State is never colour-only at the call site: it always sits
 * next to a status dot and the word "Active" / "Inactive".
 */
export function Toggle({
  checked,
  onCheckedChange,
  disabled,
  loading = false,
  size = "md",
  label,
  className,
  id,
}: ToggleProps) {
  const dimensions =
    size === "sm"
      ? { track: "h-4 w-7", knob: "h-3 w-3", travel: "translate-x-3" }
      : { track: "h-5 w-9", knob: "h-4 w-4", travel: "translate-x-4" };

  return (
    <SwitchPrimitive.Root
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled || loading}
      aria-label={label}
      aria-checked={checked}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer items-center rounded-full border border-transparent p-0.5",
        "transition-colors duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        "disabled:cursor-not-allowed disabled:opacity-50",
        dimensions.track,
        checked
          ? "bg-success-500/90"
          : "bg-neutral-500/40",
        className,
      )}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          "pointer-events-none block rounded-full bg-white shadow-elevation-1 transition-transform duration-150",
          dimensions.knob,
          checked ? dimensions.travel : "translate-x-0",
        )}
      />
    </SwitchPrimitive.Root>
  );
}

/** Colour + dot + word, so the state never depends on colour alone. */
export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-secondary">
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          active ? "bg-success-500" : "bg-neutral-500",
        )}
      />
      {active ? "Active" : "Inactive"}
    </span>
  );
}