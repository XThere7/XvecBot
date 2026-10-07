import * as React from "react";
import { cn } from "@/lib/cn";

export type DefinitionItem = {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  copyable?: string;
  /** Rendered under the value — e.g. helper text about update semantics. */
  note?: React.ReactNode;
};

export function DefinitionList({
  items,
  columns = 2,
  className,
}: {
  items: DefinitionItem[];
  columns?: 1 | 2;
  className?: string;
}) {
  return (
    <dl
      className={cn(
        "grid gap-x-8 gap-y-5",
        columns === 2 ? "sm:grid-cols-2" : "grid-cols-1",
        className,
      )}
    >
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-xs font-medium text-tertiary">{item.label}</dt>
          <dd
            className={cn(
              "mt-1.5 break-words text-base text-primary",
              item.mono && "font-mono text-sm",
            )}
          >
            {item.value ?? <span className="text-tertiary">Not set</span>}
            {item.note && (
              <p className="mt-1 text-xs text-tertiary">{item.note}</p>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}