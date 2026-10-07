"use client";

import { toast as sonnerToast } from "sonner";
import { TOAST_DURATION } from "./constants";

type Base = { title: string; description?: string; id?: string };

export const toast = {
  success: ({ title, description, id }: Base) =>
    sonnerToast.success(title, {
      description,
      id,
      duration: TOAST_DURATION.success,
    }),

  info: ({ title, description, id }: Base) =>
    sonnerToast.info(title, {
      description,
      id,
      duration: TOAST_DURATION.info,
    }),

  warning: ({ title, description, id }: Base) =>
    sonnerToast.warning(title, {
      description,
      id,
      duration: TOAST_DURATION.warning,
    }),

  error: ({ title, description, id }: Base) =>
    sonnerToast.error(title, {
      description,
      id,
      duration: TOAST_DURATION.error,
    }),

  /** Error carrying a Retry action — the only variant allowed an action button. */
  errorWithAction: ({
    title,
    description,
    onRetry,
  }: Base & { onRetry: () => void }) =>
    sonnerToast.error(title, {
      description,
      duration: TOAST_DURATION.errorWithAction,
      action: {
        label: "Retry",
        onClick: onRetry,
      },
    }),
};