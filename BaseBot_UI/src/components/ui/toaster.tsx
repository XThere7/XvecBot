"use client";

import { Toaster as SonnerToaster } from "sonner";
import { MAX_VISIBLE_TOASTS, TOAST_DURATION } from "@/lib/constants";

/**
 * Toast viewport. Durations follow §9.5 — success 3s, info/warning 4s,
 * error 6s, error-with-action 8s. Max four visible.
 * Field validation is never a toast; copy feedback is a button state change.
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      visibleToasts={MAX_VISIBLE_TOASTS}
      duration={TOAST_DURATION.success}
      closeButton
      gap={8}
      toastOptions={{
        classNames: {
          toast:
            "group rounded-md border border-subtle bg-surface-raised text-primary shadow-elevation-2",
          title: "text-base font-medium",
          description: "text-sm text-secondary",
          actionButton:
            "rounded-sm bg-accent-500 px-2.5 py-1 text-xs font-medium text-inverse",
          cancelButton: "rounded-sm px-2.5 py-1 text-xs text-secondary",
          error: "border-danger-500/40",
          success: "border-success-500/40",
          warning: "border-warning-500/40",
          info: "border-info-500/40",
        },
      }}
    />
  );
}