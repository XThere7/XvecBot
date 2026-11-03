"use client";

import * as React from "react";
import { apiGet } from "@/lib/api-client";
import { ADMIN_HOME, formatNumber } from "@/lib/admin";

type UsageSummary = {
  window_days: number;
  total_requests: number;
  error_rate: number;
  average_latency_ms: number | null;
  by_model: { model: string; n: number; avg_latency_ms: number }[];
  by_channel: { channel: string; n: number }[];
  by_day: { day: string; n: number; errors: number }[];
  top_workspaces: { workspace_id: string; workspace_name: string | null; owner_email: string | null; n: number }[];
  cost_usd_estimate: number;
  cost_estimate_note: string;
};

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  return (
    <svg
      viewBox={`0 0 ${values.length * 4} 40`}
      className="h-10 w-full"
      aria-hidden
      preserveAspectRatio="none"
    >
      <polyline
        fill="none"
        stroke="#7c84f4"
        strokeWidth="2"
        points={values
          .map((value, index) => `${index * 4},${40 - (value / max) * 38}`)
          .join(" ")}
      />
    </svg>
  );
}

export default function AdminUsagePage() {
  const [data, setData] = React.useState<UsageSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    apiGet<UsageSummary>(`${ADMIN_HOME}/usage/summary`, { skipAuthRedirect: true })
      .then(setData)
      .catch(() => setError("Could not load usage."));
  }, []);

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!data) return <p className="text-sm text-secondary">Loading usage…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Requests ({data.window_days}d)</p>
          <p className="text-xl text-primary">{formatNumber(data.total_requests)}</p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Error rate</p>
          <p className="text-xl text-primary">{(data.error_rate * 100).toFixed(2)}%</p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Avg latency</p>
          <p className="text-xl text-primary">
            {data.average_latency_ms === null ? "—" : `${data.average_latency_ms} ms`}
          </p>
        </div>
        <div className="rounded-sm border border-subtle bg-surface p-4">
          <p className="text-xs text-tertiary">Est. cost</p>
          <p className="text-xl text-primary">${data.cost_usd_estimate}</p>
        </div>
      </div>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Requests per day</h2>
        <Sparkline values={data.by_day.map((day) => day.n)} />
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">By model</h2>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-tertiary">
              <th className="py-1">Model</th>
              <th className="py-1">Requests</th>
              <th className="py-1">Avg latency</th>
            </tr>
          </thead>
          <tbody>
            {data.by_model.map((model) => (
              <tr key={model.model} className="border-t border-subtle text-secondary">
                <td className="py-1.5">{model.model}</td>
                <td className="py-1.5">{formatNumber(model.n)}</td>
                <td className="py-1.5">{Math.round(model.avg_latency_ms)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <p className="text-xs text-tertiary">{data.cost_estimate_note}</p>
    </div>
  );
}
