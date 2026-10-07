import * as React from "react";
import { cn } from "@/lib/cn";

export type PageHeaderProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
};

export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
  children,
}: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-4", className)}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl text-primary">{title}</h1>
            {meta}
          </div>
          {description && (
            <p className="mt-2 max-w-2xl text-sm leading-5 text-secondary">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
      {children}
    </header>
  );
}