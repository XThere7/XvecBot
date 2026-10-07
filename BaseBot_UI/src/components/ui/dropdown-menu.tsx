"use client";

import * as React from "react";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import { cn } from "@/lib/cn";

export type DropdownMenuItem = {
  label: string;
  onSelect: () => void;
  icon?: React.ElementType;
  tone?: "default" | "danger";
  disabled?: boolean;
  /** Rendered under the label — used for "revoke" consequences. */
  description?: string;
};

export function RowMenu({
  items,
  label = "Row actions",
  align = "end",
}: {
  items: DropdownMenuItem[];
  label?: string;
  align?: "start" | "end";
}) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger
        aria-label={label}
        className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-tertiary transition-colors hover:bg-surface-hover hover:text-primary data-[state=open]:bg-surface-hover data-[state=open]:text-primary"
      >
        <MoreHorizontal aria-hidden className="h-4 w-4" />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align={align}
          sideOffset={4}
          className="z-50 min-w-[200px] rounded-md border border-subtle bg-surface-raised p-1 shadow-elevation-2"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <DropdownMenuPrimitive.Item
                key={item.label}
                disabled={item.disabled}
                onSelect={item.onSelect}
                className={cn(
                  "flex cursor-pointer select-none items-start gap-2 rounded-sm px-2 py-1.5 text-sm outline-none",
                  "data-[highlighted]:bg-surface-hover data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                  item.tone === "danger"
                    ? "text-danger-400 data-[highlighted]:bg-danger-500/10"
                    : "text-primary",
                )}
              >
                {Icon && <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />}
                <span className="min-w-0">
                  <span className="block">{item.label}</span>
                  {item.description && (
                    <span className="mt-0.5 block text-2xs text-tertiary">
                      {item.description}
                    </span>
                  )}
                </span>
              </DropdownMenuPrimitive.Item>
            );
          })}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}