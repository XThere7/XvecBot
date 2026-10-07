"use client";

import { PageHeader } from "@/components/common/page-header";
import { AlertBanner } from "@/components/ui/alert-banner";
import { API_BASE_URL } from "@/lib/api-client";
import { SITE_URL } from "@/lib/constants";

export default function AccountSecurityPage() {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Session &amp; API"
        description="How this dashboard talks to the backend."
      />

      <AlertBanner tone="info" title="CORS">
        The backend does not allow any origin for dashboard calls. If a request
        fails with <code className="font-mono">Disallowed CORS origin</code>,
        add this dashboard&apos;s origin to{" "}
        <code className="font-mono">ALLOWED_ORIGINS</code> in the backend
        <code className="font-mono"> .env</code> and restart it.
      </AlertBanner>

      <section className="rounded-md border border-subtle bg-surface p-6">
        <h2 className="text-lg text-primary">Configuration</h2>
        <dl className="mt-4 flex flex-col gap-4">
          <div>
            <dt className="text-xs text-tertiary">NEXT_PUBLIC_API_BASE_URL</dt>
            <dd className="mt-1 font-mono text-sm text-primary">{API_BASE_URL}</dd>
          </div>
          <div>
            <dt className="text-xs text-tertiary">NEXT_PUBLIC_SITE_URL</dt>
            <dd className="mt-1 font-mono text-sm text-primary">
              {SITE_URL || "—"}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs leading-5 text-tertiary">
          Any variable prefixed{" "}
          <code className="font-mono">NEXT_PUBLIC_</code> is compiled into the
          client bundle and is publicly readable. Backend secrets — the
          OpenRouter key, the JWT secret — must never be placed there.
        </p>
      </section>
    </div>
  );
}