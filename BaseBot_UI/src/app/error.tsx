"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/common/error-panel";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Nothing is logged with token data — only the error digest.
    console.error(error.message);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-dvh max-w-xl items-center px-5">
      <div className="w-full">
        <ErrorPanel
          title="Something went wrong"
          message="The page could not be rendered. Trying again usually fixes it."
          onRetry={reset}
        />
        <div className="mt-4 text-center">
          <Button asChild variant="ghost">
            <a href="/dashboard">Back to dashboard</a>
          </Button>
        </div>
      </div>
    </div>
  );
}
