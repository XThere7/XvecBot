import * as React from "react";
import Link from "next/link";
import { FileQuestion } from "lucide-react";
import { cn } from "@/lib/cn";

/** Dedicated 404 state — resource-specific, never a generic error block. */
export function NotFoundPanel({
  title,
  description,
  backHref,
  backLabel = "Go back",
  className,
}: {
  title: string;
  description: string;
  backHref: string;
  backLabel?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-md border border-subtle bg-surface px-6 py-16 text-center",
        className,
      )}
    >
      <FileQuestion aria-hidden className="h-8 w-8 text-tertiary" />
      <div>
        <p className="text-lg font-semibold text-primary">{title}</p>
        <p className="mt-2 max-w-md text-sm leading-5 text-secondary">{description}</p>
      </div>
      <Link
        href={backHref}
        className="mt-2 inline-flex h-[38px] items-center rounded-sm border border-subtle bg-surface-raised px-4 text-base text-primary transition-colors hover:bg-surface-hover hover:border-strong"
      >
        {backLabel}
      </Link>
    </div>
  );
}