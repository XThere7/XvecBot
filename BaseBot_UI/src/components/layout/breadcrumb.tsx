import * as React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

export type Crumb = { label: string; href?: string };

export function Breadcrumb({
  items,
  maxItems = 4,
  className,
}: {
  items: Crumb[];
  maxItems?: number;
  className?: string;
}) {
  const truncated = items.length > maxItems;
  const visible: (Crumb | "overflow")[] = truncated
    ? ["overflow", ...items.slice(items.length - (maxItems - 1))]
    : items;

  return (
    <nav aria-label="Breadcrumb" className={cn("min-w-0", className)}>
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {visible.map((item, index) => {
          const isLast = index === visible.length - 1;
          return (
            <li key={isLast ? "last" : index} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && (
                <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-tertiary" />
              )}
              {item === "overflow" ? (
                <span aria-hidden className="text-tertiary">
                  …
                </span>
              ) : isLast || !item.href ? (
                <span
                  aria-current={isLast ? "page" : undefined}
                  className={cn("truncate", isLast ? "text-primary" : "text-tertiary")}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  href={item.href}
                  className="truncate text-secondary transition-colors hover:text-primary"
                >
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}