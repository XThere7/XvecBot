"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

type FieldContextValue = {
  controlId: string;
  describedBy?: string;
  invalid: boolean;
};

const FieldContext = React.createContext<FieldContextValue | null>(null);

/**
 * Controls read their id / aria wiring from the nearest FieldControl, so every
 * input in the product is labelled and described identically.
 */
export function useFieldProps(override?: {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}) {
  const context = React.useContext(FieldContext);
  return {
    id: override?.id ?? context?.controlId,
    "aria-describedby":
      override?.["aria-describedby"] ?? context?.describedBy ?? undefined,
    "aria-invalid":
      override?.["aria-invalid"] ?? (context?.invalid ? true : undefined),
  };
}

type FieldProps = {
  label?: string;
  hint?: React.ReactNode;
  error?: string;
  required?: boolean;
  counter?: React.ReactNode;
  className?: string;
};

/** The single label → control → helper/error composition used by every form. */
export function FieldControl({
  label,
  hint,
  error,
  required,
  counter,
  className,
  children,
}: FieldProps & { children: React.ReactNode }) {
  const generatedId = React.useId();
  const controlId = `field-${generatedId}`;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {(label || counter) && (
        <div className="flex items-baseline justify-between gap-3">
          {label && (
            <label htmlFor={controlId} className="text-xs font-medium text-secondary">
              {label}
              {required && (
                <span className="ml-0.5 text-danger-400" aria-hidden>
                  *
                </span>
              )}
            </label>
          )}
          {counter && <span className="text-2xs text-tertiary">{counter}</span>}
        </div>
      )}

      <FieldContext.Provider
        value={{ controlId, describedBy, invalid: Boolean(error) }}
      >
        {children}
      </FieldContext.Provider>

      {error ? (
        <p id={errorId} className="text-xs text-danger-400">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-tertiary">
          {hint}
        </p>
      ) : null}
    </div>
  );
}