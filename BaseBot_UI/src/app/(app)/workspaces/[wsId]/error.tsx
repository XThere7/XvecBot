"use client";

import { ErrorPanel } from "@/components/common/error-panel";

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorPanel
      title="This workspace could not be loaded"
      message={
        error.message ||
        "The page hit an unexpected error. Trying again usually fixes it."
      }
      statusCode={(error as { status?: number }).status}
      onRetry={reset}
    />
  );
}
