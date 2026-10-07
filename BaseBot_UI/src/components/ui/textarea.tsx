"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { useFieldProps } from "./field";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean;
  autoResize?: boolean;
};

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ className, invalid, autoResize = false, onChange, rows = 4, ...props }, ref) {
    const field = useFieldProps();
    const innerRef = React.useRef<HTMLTextAreaElement | null>(null);
    const setRefs = React.useCallback(
      (node: HTMLTextAreaElement | null) => {
        innerRef.current = node;
        if (typeof ref === "function") ref(node);
        else if (ref) ref.current = node;
      },
      [ref],
    );

    const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange?.(event);
      if (autoResize) {
        const node = event.target;
        node.style.height = "auto";
        node.style.height = `${node.scrollHeight}px`;
      }
    };

    return (
      <textarea
        ref={setRefs}
        id={props.id ?? field.id}
        aria-describedby={props["aria-describedby"] ?? field["aria-describedby"]}
        rows={rows}
        aria-invalid={invalid || field["aria-invalid"]}
        onChange={handleChange}
        className={cn(
          "w-full resize-y rounded-sm border bg-inset px-3 py-2 text-base leading-5 text-primary",
          "placeholder:text-tertiary",
          "transition-colors duration-150",
          "focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent-500",
          "disabled:cursor-not-allowed disabled:opacity-50",
          invalid
            ? "border-danger-500 focus-visible:outline-danger-500"
            : "border-strong hover:border-tertiary focus:border-accent-500",
          autoResize && "resize-none overflow-hidden",
          className,
        )}
        {...props}
      />
    );
  },
);