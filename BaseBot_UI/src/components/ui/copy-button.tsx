"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/cn";

export type CopyButtonProps = {
  value: string;
  label?: React.ReactNode;
  /** Announced and shown while the value sits in the clipboard. */
  copiedLabel?: React.ReactNode;
  variant?: "secondary" | "ghost" | "primary";
  size?: "sm" | "md";
  className?: string;
  onCopied?: () => void;
  title?: string;
};

async function writeClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  // Fallback for insecure origins.
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  document.body.removeChild(area);
}

/** Copy feedback is a button state change, never a toast. */
export function CopyButton({
  value,
  label = "Copy",
  copiedLabel = "Copied",
  variant = "secondary",
  size = "sm",
  className,
  onCopied,
  title,
}: CopyButtonProps) {
  const [copied, setCopied] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleCopy = async () => {
    try {
      await writeClipboard(value);
      setCopied(true);
      onCopied?.();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={title}
      aria-live="polite"
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-sm border font-medium transition-colors duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        "disabled:pointer-events-none disabled:opacity-50",
        size === "sm"
          ? "h-8 max-sm:h-11 px-2.5 max-sm:px-3 text-xs"
          : "h-[38px] max-sm:h-11 px-3.5 text-sm",
        variant === "primary"
          ? "border-accent-500 bg-accent-500 text-inverse hover:bg-accent-400"
          : variant === "ghost"
            ? "border-transparent bg-transparent text-secondary hover:bg-surface-hover hover:text-primary"
            : copied
              ? "border-success-500/40 bg-success-500/10 text-success-400"
              : "border-subtle bg-surface-raised text-primary hover:bg-surface-hover hover:border-strong",
        className,
      )}
    >
      {copied ? (
        <Check aria-hidden className="h-3.5 w-3.5" />
      ) : (
        <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none">
          <rect
            x="5.25"
            y="5.25"
            width="7.5"
            height="7.5"
            rx="1.5"
            stroke="currentColor"
            strokeWidth="1.25"
          />
          <path
            d="M10.75 3.25h-6A1.5 1.5 0 003.25 4.75v6"
            stroke="currentColor"
            strokeWidth="1.25"
            strokeLinecap="round"
          />
        </svg>
      )}
      {copied ? copiedLabel : label}
    </button>
  );
}