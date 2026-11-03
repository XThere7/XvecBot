"use client";

import * as React from "react";
import { apiGet } from "@/lib/api-client";
import { ADMIN_HOME, formatEAT, formatNumber } from "@/lib/admin";

type SystemHealth = {
  api: { status: string; version: string };
  database: {
    engine: string;
    size_bytes: number | null;
    uploads_size_bytes: number | null;
    vector_size_bytes: number | null;
    disk_free_bytes: number;
  };
  background_jobs: Record<string, number>;
  recent_errors: { id: string; ts: string; path: string; status: number | null; exception_type: string; message: string }[];
  email: { backend: string; from_address: string | null; smtp_configured: boolean };
  model_provider: { status: string; note: string };
  rate_limiting: { enabled: boolean; per_minute: number };
};

function mb(bytes: number | null): string {
  return bytes === null ? "—" : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function AdminSystemPage() {
  const [data, setData] = React.useState<SystemHealth | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    apiGet<SystemHealth>(`${ADMIN_HOME}/system/health`, { skipAuthRedirect: true })
      .then(setData)
      .catch(() => setError("Could not load system health."));
  }, []);

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!data) return <p className="text-sm text-secondary">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">API</p>
          <p className="text-lg text-primary">{data.api.status}</p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Database</p>
          <p className="text-lg text-primary">{data.database.engine}</p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">DB size</p>
          <p className="text-lg text-primary">{mb(data.database.size_bytes)}</p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Disk free</p>
          <p className="text-lg text-primary">{mb(data.database.disk_free_bytes)}</p>
        </div>
      </div>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Background jobs</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
          {Object.entries(data.background_jobs).map(([kind, count]) => (
            <div key={kind} className="flex justify-between gap-2">
              <dt className="text-tertiary">{kind}</dt>
              <dd className={count > 0 ? "text-danger-400" : "text-secondary"}>
                {formatNumber(count)}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Email</h2>
        <p className="text-sm text-secondary">
          Backend <strong>{data.email.backend}</strong> · From{" "}
          {data.email.from_address ?? "—"} · SMTP{" "}
          {data.email.smtp_configured ? "configured" : "not configured"}
        </p>
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Recent server errors</h2>
        {data.recent_errors.length === 0 ? (
          <p className="text-sm text-secondary">No recorded errors.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm text-secondary">
            {data.recent_errors.slice(0, 10).map((item) => (
              <li key={item.id} className="flex justify-between gap-3">
                <span className="truncate">
                  {formatEAT(item.ts)} · {item.path} · {item.exception_type}
                </span>
                <span className="shrink-0 text-tertiary">{item.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-tertiary">
        {data.model_provider.note} · Rate limiter:{" "}
        {data.rate_limiting.enabled ? `on (${data.rate_limiting.per_minute}/min)` : "off"}
      </p>
    </div>
  );
}
