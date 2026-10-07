"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { useFieldProps } from "./field";

export type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & {
  invalid?: boolean;
  prefixIcon?: React.ReactNode;
  endAdornment?: React.ReactNode;
  inputSize?: "sm" | "md";
};

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, prefixIcon, endAdornment, inputSize = "md", ...props },
  ref,
) {
  const field = useFieldProps();

  const control = (
    <input
      ref={ref}
      id={props.id ?? field.id}
      aria-describedby={props["aria-describedby"] ?? field["aria-describedby"]}
      aria-invalid={invalid || field["aria-invalid"]}
      className={cn(
        "w-full rounded-sm border bg-inset text-primary",
        "placeholder:text-tertiary",
        "transition-colors duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent-500",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "read-only:cursor-default read-only:text-secondary",
        invalid
          ? "border-danger-500 focus-visible:outline-danger-500"
          : "border-strong hover:border-tertiary focus:border-accent-500",
        inputSize === "sm" ? "h-8 px-2.5 text-sm" : "h-[38px] px-3 text-base",
        prefixIcon && "pl-9",
        endAdornment && "pr-9",
        className,
      )}
      {...props}
    />
  );

  if (!prefixIcon && !endAdornment) return control;

  return (
    <div className="relative">
      {prefixIcon && (
        <span
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-tertiary [&>svg]:h-4 [&>svg]:w-4"
        >
          {prefixIcon}
        </span>
      )}
      {control}
      {endAdornment && (
        <span className="absolute right-1.5 top-1/2 -translate-y-1/2 text-tertiary">
          {endAdornment}
        </span>
      )}
    </div>
  );
});