"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";
import { useFieldProps } from "./field";

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  /** Rendered in a dimmer weight next to the label — used for model notes. */
  note?: string;
};

export type SelectGroup = { label: string; options: SelectOption[] };

type SelectProps = {
  options: SelectOption[];
  groups?: SelectGroup[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
  id?: string;
  "aria-describedby"?: string;
};

export function Select({
  options,
  groups,
  value,
  onValueChange,
  placeholder = "Select…",
  disabled,
  invalid,
  className,
  id,
  ...aria
}: SelectProps) {
  const allOptions = groups ? groups.flatMap((g) => g.options) : options;
  const field = useFieldProps();

  return (
    <SelectPrimitive.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        id={id ?? field.id}
        aria-invalid={invalid || field["aria-invalid"] || undefined}
        aria-describedby={aria["aria-describedby"] ?? field["aria-describedby"]}
        className={cn(
          "flex h-[38px] w-full items-center justify-between gap-2 rounded-sm border bg-inset px-3 text-base text-primary",
          "transition-colors duration-150",
          "focus:outline-2 focus:outline-offset-0 focus:outline-accent-500",
          "disabled:cursor-not-allowed disabled:opacity-50",
          invalid
            ? "border-danger-500"
            : "border-strong hover:border-tertiary focus:border-accent-500",
          "[&>span]:truncate",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon asChild>
          <ChevronDown aria-hidden className="h-4 w-4 shrink-0 text-tertiary" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className={cn(
            "z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden",
            "rounded-md border border-subtle bg-surface-raised shadow-elevation-2",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          )}
        >
          <SelectPrimitive.Viewport className="p-1">
            {groups ? (
              groups.map((group) => (
                <SelectPrimitive.Group key={group.label}>
                  <SelectPrimitive.Label className="px-2 py-1.5 text-2xs uppercase tracking-wide text-tertiary">
                    {group.label}
                  </SelectPrimitive.Label>
                  {group.options.map((option) => (
                    <SelectItem
                      key={option.value}
                      value={option.value}
                      disabled={option.disabled}
                      note={option.note}
                    >
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectPrimitive.Group>
              ))
            ) : (
              allOptions.map((option) => (
                <SelectItem
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  note={option.note}
                >
                  {option.label}
                </SelectItem>
              ))
            )}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

function SelectItem({
  children,
  note,
  ...props
}: SelectPrimitive.SelectItemProps & { note?: string }) {
  return (
    <SelectPrimitive.Item
      {...props}
      className={cn(
        "relative flex cursor-pointer select-none items-center gap-2 rounded-sm py-2 pl-8 pr-2 text-base text-primary outline-none",
        "data-[highlighted]:bg-surface-hover data-[highlighted]:text-primary",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      )}
    >
      <span className="absolute left-2 flex h-4 w-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check aria-hidden className="h-4 w-4 text-accent-400" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      {note && <span className="ml-auto text-2xs text-tertiary">{note}</span>}
    </SelectPrimitive.Item>
  );
}