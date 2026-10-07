"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export type ModalSize = "sm" | "md" | "lg" | "xl";

const SIZE_CLASSES: Record<ModalSize, string> = {
  sm: "max-w-[400px]",
  md: "max-w-[560px]",
  lg: "max-w-[720px]",
  xl: "max-w-[900px]",
};

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  size?: ModalSize;
  footer?: React.ReactNode;
  /** Esc / overlay dismissal. The one-time credential modal sets this false. */
  dismissible?: boolean;
  closeOnOverlay?: boolean;
  children?: React.ReactNode;
  className?: string;
  hideCloseButton?: boolean;
  bodyClassName?: string;
  /** CSS selector for the element that receives focus on open. */
  initialFocusSelector?: string;
};

export function Modal({
  open,
  onClose,
  title,
  description,
  size = "md",
  footer,
  dismissible = true,
  closeOnOverlay = true,
  children,
  className,
  hideCloseButton = false,
  bodyClassName,
  initialFocusSelector,
}: ModalProps) {
  const reduceMotion = useReducedMotion();
  const contentRef = React.useRef<HTMLDivElement | null>(null);

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (next || dismissible) onClose();
      }}
    >
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild>
              <motion.div
                initial={reduceMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15, ease: "easeOut" }}
                className="fixed inset-0 z-50 bg-black/70"
              />
            </DialogPrimitive.Overlay>

            {/* Centring lives here so the panel's own transform is free for
                the scale/fade entrance. */}
            <DialogPrimitive.Content
              asChild
              onEscapeKeyDown={(event) => {
                if (!dismissible) event.preventDefault();
              }}
              onPointerDownOutside={(event) => {
                if (!closeOnOverlay || !dismissible) event.preventDefault();
              }}
              onInteractOutside={(event) => {
                if (!closeOnOverlay || !dismissible) event.preventDefault();
              }}
              onOpenAutoFocus={
                initialFocusSelector
                  ? (event) => {
                      const target = contentRef.current?.querySelector<HTMLElement>(
                        initialFocusSelector,
                      );
                      if (target) {
                        event.preventDefault();
                        target.focus();
                      }
                    }
                  : undefined
              }
            >
              <div
                ref={contentRef}
                className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4 max-sm:p-0"
              >
                <motion.div
                  initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={reduceMotion ? { opacity: 1 } : { opacity: 0, scale: 0.98 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  className={cn(
                    "pointer-events-auto flex max-h-[90dvh] w-full flex-col overflow-hidden",
                    "rounded-lg border border-subtle bg-surface-raised shadow-elevation-3",
                    "max-sm:h-[100dvh] max-sm:max-h-none max-sm:rounded-none",
                    SIZE_CLASSES[size],
                    className,
                  )}
                >
                  <header className="flex items-start justify-between gap-4 border-b border-subtle px-6 py-4 max-sm:px-4">
                    <div className="min-w-0">
                      <DialogPrimitive.Title className="text-lg text-primary">
                        {title}
                      </DialogPrimitive.Title>
                      {description && (
                        <DialogPrimitive.Description className="mt-1 text-sm text-secondary">
                          {description}
                        </DialogPrimitive.Description>
                      )}
                    </div>
                    {!hideCloseButton && dismissible && (
                      <DialogPrimitive.Close
                        aria-label="Close"
                        className="-mr-1 -mt-1 rounded-sm p-1.5 text-tertiary transition-colors hover:bg-surface-hover hover:text-primary"
                      >
                        <X aria-hidden className="h-4 w-4" />
                      </DialogPrimitive.Close>
                    )}
                  </header>

                  <div
                    className={cn(
                      "min-h-0 flex-1 overflow-y-auto px-6 py-5",
                      bodyClassName ?? "max-sm:px-4",
                    )}
                  >
                    {children}
                  </div>

                  {footer && (
                    <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-subtle bg-surface px-6 py-4 max-sm:sticky max-sm:bottom-0 max-sm:px-4">
                      {footer}
                    </footer>
                  )}
                </motion.div>
              </div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}