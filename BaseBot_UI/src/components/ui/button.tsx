"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "dangerGhost"
  | "link";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-accent-500 text-inverse font-medium hover:bg-accent-400 active:bg-accent-600 disabled:hover:bg-accent-500",
  secondary:
    "bg-surface-raised text-primary border border-subtle hover:bg-surface-hover hover:border-strong active:bg-surface-raised",
  ghost: "text-secondary hover:bg-surface-hover hover:text-primary",
  danger:
    "bg-danger-500 text-white font-medium hover:bg-danger-400 active:bg-danger-500",
  dangerGhost:
    "text-danger-400 border border-danger-500/40 hover:bg-danger-500/10 hover:border-danger-500/70",
  link: "text-accent-300 underline-offset-4 hover:underline p-0 h-auto",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  // 44px minimum touch target on mobile (WCAG 2.5.5 target size).
  sm: "h-8 max-sm:h-11 px-3 max-sm:px-3.5 text-sm gap-1.5 rounded-sm",
  md: "h-[38px] max-sm:h-11 px-4 text-base gap-2 rounded-sm",
  lg: "h-11 px-5 text-base gap-2 rounded-sm",
};

const BASE_CLASSES =
  "relative inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500 disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  fullWidth?: boolean;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  asChild?: boolean;
};

type ChildProps = {
  className?: string;
  children?: React.ReactNode;
  [key: string]: unknown;
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      loading = false,
      fullWidth = false,
      iconLeft,
      iconRight,
      asChild = false,
      className,
      children,
      disabled,
      type = "button",
      ...props
    },
    ref,
  ) {
    const isDisabled = disabled || loading;

    const classes = cn(
      BASE_CLASSES,
      VARIANT_CLASSES[variant],
      variant !== "link" && SIZE_CLASSES[size],
      fullWidth && "w-full",
      className,
    );

    /*
     * asChild is implemented with cloneElement instead of Radix Slot on
     * purpose: Slot clones its single child and merges every prop onto it, so
     * composing iconLeft/iconRight in a Fragment here would hand that Fragment
     * the button's type/disabled/className — and a Fragment rejects all three
     * ("Invalid prop `type` supplied to React.Fragment"). Cloning the
     * consumer's own element keeps icons working and never involves a Fragment.
     */
    if (asChild && React.isValidElement<ChildProps>(children)) {
      const content = loading ? (
        <>
          <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
          {children.props.children}
        </>
      ) : (
        <>
          {iconLeft}
          {children.props.children}
          {iconRight}
        </>
      );

      return React.cloneElement(children, {
        ...props,
        ref,
        "aria-disabled": isDisabled || undefined,
        "aria-busy": loading || undefined,
        "data-loading": loading ? "" : undefined,
        className: cn(classes, children.props.className),
        children: content,
      });
    }

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-busy={loading || undefined}
        data-loading={loading ? "" : undefined}
        className={classes}
        {...props}
      >
        {loading ? (
          /* The spinner replaces the leading icon; the label stays so the
             button width never changes mid-request. */
          <>
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            {children}
          </>
        ) : (
          <>
            {iconLeft}
            {children}
            {iconRight}
          </>
        )}
      </button>
    );
  },
);
