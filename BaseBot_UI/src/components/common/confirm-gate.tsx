"use client";

import * as React from "react";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

export type ConfirmRequest = {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  onConfirm: () => void;
};

/**
 * Owns the state of a single confirmation dialog. Every destructive or
 * service-affecting action in the product goes through this gate, so the
 * mandated copy and the "cancel holds focus" rule live in exactly one place.
 */
export function useConfirmGate() {
  const [request, setRequest] = React.useState<ConfirmRequest | null>(null);
  const [pending, setPending] = React.useState(false);

  const close = React.useCallback(() => setRequest(null), []);

  const ask = React.useCallback((next: ConfirmRequest) => setRequest(next), []);

  const confirm = React.useCallback(async () => {
    if (!request) return;
    setPending(true);
    try {
      await request.onConfirm();
    } finally {
      setPending(false);
      setRequest(null);
    }
  }, [request]);

  const dialog = request ? (
    <ConfirmationDialog
      open
      onClose={close}
      title={request.title}
      body={request.body}
      confirmLabel={request.confirmLabel}
      cancelLabel={request.cancelLabel}
      variant={request.variant}
      confirmLoading={pending}
      onConfirm={() => void confirm()}
    />
  ) : null;

  return { ask, close, dialog, pending };
}
