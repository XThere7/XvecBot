"use client";

import * as React from "react";
import { Button } from "./button";
import { Modal } from "./modal";

export type ConfirmationDialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  /** May be a string or a list of consequences. */
  body: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  onConfirm: () => void;
  confirmLoading?: boolean;
};

/**
 * Mandatory gate before every destructive or service-affecting action.
 * Cancel holds initial focus; confirm is never autofocused.
 */
export function ConfirmationDialog({
  open,
  onClose,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "danger",
  onConfirm,
  confirmLoading = false,
}: ConfirmationDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      className="max-w-[440px]"
      /* Land focus on Cancel — the confirm button is never autofocused. */
      initialFocusSelector='[data-autofocus="true"]'
      footer={
        <>
          <Button
            data-autofocus="true"
            variant="secondary"
            onClick={onClose}
            disabled={confirmLoading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={confirmLoading}
            disabled={confirmLoading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-5 text-secondary">{body}</div>
    </Modal>
  );
}