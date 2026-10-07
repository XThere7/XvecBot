import { AlertTriangle } from "lucide-react";
import { API_BASE_URL } from "@/lib/api-client";
import { APP_NAME } from "@/lib/constants";

/**
 * Rendered instead of the app when NEXT_PUBLIC_API_BASE_URL is missing — a
 * missing variable must not surface as a confusing network error on every page.
 */
export function ConfigError() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-5">
      <div className="w-full max-w-lg rounded-md border border-warning-500/30 bg-surface p-6">
        <div className="flex items-center gap-3">
          <AlertTriangle aria-hidden className="h-5 w-5 text-warning-400" />
          <h1 className="text-lg text-primary">Configuration error</h1>
        </div>
        <p className="mt-3 text-sm leading-5 text-secondary">
          {APP_NAME} needs the address of its backend API before it can load.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-sm border border-subtle bg-inset px-3 py-2.5 font-mono text-xs text-primary">
          {`# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`}
        </pre>
        <p className="mt-3 text-xs text-tertiary">
          No trailing slash. The backend must be reachable from the browser, and
          this origin must be listed in the backend&apos;s{" "}
          <code className="font-mono">ALLOWED_ORIGINS</code>. Current value:{" "}
          <code className="font-mono">{API_BASE_URL || "—"}</code>
        </p>
      </div>
    </div>
  );
}