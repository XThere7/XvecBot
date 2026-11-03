"use client";

import * as React from "react";
import { apiPost } from "@/lib/api-client";
import { AdminDataTable } from "@/components/admin/admin-data-table";
import { formatEAT, formatTzs } from "@/lib/admin";
import { ADMIN_HOME, useAdminMe } from "@/lib/admin";

type SubscriptionRow = {
  id: string;
  email: string;
  plan: string;
  trial_ends_at: string | null;
  suspended_at: string | null;
};

type PaymentRow = {
  id: string;
  email: string;
  amount_tzs: number;
  method: string;
  reference: string | null;
  recorded_at: string;
};

export default function AdminSubscriptionsPage() {
  const { me } = useAdminMe();
  const canBill = me?.role === "superadmin" || me?.permissions.includes("billing.manage");
  const [paying, setPaying] = React.useState(false);
  const [note, setNote] = React.useState<string | null>(null);

  async function recordPayment(userId: string, email: string) {
    const amount = Number(window.prompt(`Amount in TZS for ${email}:`) || "0");
    if (!amount) return;
    const method = window.prompt("Method (mpesa/tigo/airtel/bank/cash/other):") || "cash";
    const reference = window.prompt("Reference (optional):") || "";
    setPaying(true);
    setNote(null);
    try {
      await apiPost(
        `${ADMIN_HOME}/payments/${userId}`,
        { amount_tzs: amount, method, reference },
        { skipAuthRedirect: true },
      );
      setNote("Payment recorded.");
    } catch {
      setNote("Could not record the payment.");
    } finally {
      setPaying(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <AdminDataTable<SubscriptionRow>
        title="Subscriptions and trials"
        path="/subscriptions"
        columns={[
          { key: "email", header: "Email", render: (row) => row.email },
          { key: "plan", header: "Plan", render: (row) => row.plan },
          { key: "trial", header: "Trial ends", render: (row) => formatEAT(row.trial_ends_at) },
          {
            key: "status",
            header: "Status",
            render: (row) =>
              row.suspended_at ? (
                <span className="text-danger-400">Suspended</span>
              ) : (
                <span className="text-secondary">Active</span>
              ),
          },
        ]}
        actions={(row) =>
          canBill ? (
            <button
              type="button"
              disabled={paying}
              onClick={() => recordPayment(row.id, row.email)}
              className="text-xs text-accent-300 hover:underline"
            >
              Record payment
            </button>
          ) : null
        }
      />
      {note && <p className="text-sm text-secondary">{note}</p>}
      <AdminDataTable<PaymentRow>
        title="Payments"
        path="/payments"
        columns={[
          { key: "email", header: "User", render: (row) => row.email },
          { key: "amount", header: "Amount", render: (row) => formatTzs(row.amount_tzs) },
          { key: "method", header: "Method", render: (row) => row.method },
          { key: "reference", header: "Reference", render: (row) => row.reference ?? "—" },
          { key: "recorded", header: "Recorded", render: (row) => formatEAT(row.recorded_at) },
        ]}
      />
    </div>
  );
}
