import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

export function ErrorPanel({
  title = "Something went wrong",
  message,
  statusCode,
  onRetry,
  className,
  compact = false,
}: {
  title?: string;
  message?: string;
  statusCode?: number;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-md border border-danger-500/30 bg-danger-500/5 text-center",
        compact ? "px-4 py-6" : "px-6 py-14",
        className,
      )}
    >
      <AlertTriangle aria-hidden className="h-6 w-6 text-danger-400" />
      <div>
        <p className="text-base font-medium text-primary">{title}</p>
        {message && (
          <p className="mt-1 max-w-md text-sm leading-5 text-secondary">{message}</p>
        )}
        {typeof statusCode === "number" && (
          <p className="mt-2 font-mono text-2xs text-tertiary">
            HTTP {statusCode}
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}