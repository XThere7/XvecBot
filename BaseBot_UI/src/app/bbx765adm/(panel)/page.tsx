"use client";

import * as React from "react";
import { apiGet } from "@/lib/api-client";
import { ADMIN_HOME, formatNumber, formatTzs } from "@/lib/admin";

type Overview = {
  totals: Record<string, number>;
  plans: Record<string, number>;
  trials: Record<string, number>;
  chat: Record<string, number>;
  chat_by_channel_90d: Record<string, number>;
  error_rate_30d: number;
  average_latency_ms_30d: number | null;
  estimated_monthly_revenue_tzs: number;
  estimated_monthly_revenue_note: string;
  needs_attention: { kind: string; count: number }[];
};

function Card({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-subtle bg-surface p-4">
      <p className="text-xs text-tertiary">{label}</p>
      <p className="mt-1 text-xl text-primary">{value}</p>
    </div>
  );
}

export default function AdminOverviewPage() {
  const [data, setData] = React.useState<Overview | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    apiGet<Overview>(`${ADMIN_HOME}/overview`, { skipAuthRedirect: true })
      .then(setData)
      .catch(() => setError("Could not load the overview."));
  }, []);

  if (error) {
    return <p className="text-sm text-danger-400">{error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-secondary">Loading overview…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card label="Users" value={formatNumber(data.totals.users)} />
        <Card label="Signups (30d)" value={formatNumber(data.totals.signups_30d)} />
        <Card label="Workspaces" value={formatNumber(data.totals.workspaces)} />
        <Card label="Chat requests (30d)" value={formatNumber(data.chat["30d"])} />
        <Card label="Agents" value={formatNumber(data.totals.agents)} />
        <Card label="Documents" value={formatNumber(data.totals.documents)} />
        <Card label="Suspended accounts" value={formatNumber(data.totals.suspended)} />
        <Card
          label="Est. monthly revenue"
          value={formatTzs(data.estimated_monthly_revenue_tzs)}
        />
        <Card label="Error rate (30d)" value={`${(data.error_rate_30d * 100).toFixed(2)}%`} />
        <Card
          label="Avg latency (30d)"
          value={
            data.average_latency_ms_30d === null
              ? "—"
              : `${data.average_latency_ms_30d} ms`
          }
        />
        <Card label="Active trials" value={formatNumber(data.trials.active)} />
        <Card label="Trials expiring (7d)" value={formatNumber(data.totals.trials_expiring_7d)} />
      </div>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Needs attention</h2>
        <ul className="flex flex-col gap-1 text-sm text-secondary">
          {data.needs_attention.map((item) => (
            <li key={item.kind} className="flex justify-between gap-4">
              <span className="text-tertiary">{item.kind}</span>
              <span className={item.count > 0 ? "text-danger-400" : undefined}>
                {formatNumber(item.count)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">Chat by channel (90d)</h2>
        <div className="flex flex-wrap gap-2 text-sm text-secondary">
          {Object.entries(data.chat_by_channel_90d).map(([channel, count]) => (
            <span key={channel} className="rounded-sm bg-inset px-2 py-1">
              {channel}: <strong>{formatNumber(count)}</strong>
            </span>
          ))}
        </div>
      </section>

      <p className="text-xs text-tertiary">
        {data.estimated_monthly_revenue_note} · Times shown in East Africa Time.
      </p>
    </div>
  );
}
