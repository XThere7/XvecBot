"use client";

import * as React from "react";
import { apiGet, apiPost } from "@/lib/api-client";
import { ADMIN_HOME, useAdminMe, formatEAT } from "@/lib/admin";

type ActivityRow = {
  ts: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  summary: string;
  ip: string | null;
};

export default function AdminMyAccountPage() {
  const { me, reload } = useAdminMe();
  const [activity, setActivity] = React.useState<ActivityRow[] | null>(null);
  const [setup, setSetup] = React.useState<{ secret: string; qr_data_uri: string } | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    apiGet<{ items: ActivityRow[] }>(`${ADMIN_HOME}/my-account/activity`, {
      skipAuthRedirect: true,
    })
      .then((data) => setActivity(data.items))
      .catch(() => setActivity([]));
  }, []);

  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    setBusy(true);
    setNote(null);
    try {
      await apiPost(
        `${ADMIN_HOME}/my-account/password`,
        {
          current_password: form.current.value,
          new_password: form.next.value,
          confirm_password: form.confirm.value,
        },
        { skipAuthRedirect: true },
      );
      setNote("Password changed. Other sessions were signed out.");
      form.reset();
    } catch (err) {
      const detail = (err as { body?: { detail?: string } })?.body?.detail;
      setNote(detail ?? "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  async function startTotp() {
    const password = window.prompt("Your password to confirm:") || "";
    setBusy(true);
    setNote(null);
    try {
      const data = await apiPost<{ secret: string; qr_data_uri: string }>(
        `${ADMIN_HOME}/my-account/totp/setup`,
        { reauth_password: password },
        { skipAuthRedirect: true },
      );
      setSetup(data);
    } catch (err) {
      const status = (err as { status?: number })?.status;
      setNote(status === 403 ? "Re-authentication failed." : "Could not start setup.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyTotp() {
    setBusy(true);
    setNote(null);
    try {
      const data = await apiPost<{ recovery_codes: string[] }>(
        `${ADMIN_HOME}/my-account/totp/verify`,
        { code },
        { skipAuthRedirect: true },
      );
      setSetup(null);
      setCode("");
      reload();
      const codes = data.recovery_codes;
      setNote(
        `Two-factor enabled. Single-use recovery codes: ${codes.join(" ")} (store them now)`,
      );
    } catch {
      setNote("Invalid code.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="text-lg text-primary">{me?.email}</h2>
        <p className="mt-1 text-sm text-secondary">
          Role: <strong>{me?.role}</strong> · 2FA:{" "}
          {me?.totp_enabled ? (
            <span className="text-accent-300">enabled</span>
          ) : (
            "not enabled"
          )}
        </p>
        {me?.role !== "superadmin" && (
          <p className="mt-1 text-xs text-tertiary">
            Permissions: {(me?.permissions ?? []).join(", ") || "none"}
          </p>
        )}
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">
          Two-factor authentication
        </h2>
        {!me?.totp_enabled && !setup && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void startTotp()}
            className="rounded-sm bg-accent-500 px-3 py-2 text-sm font-medium text-white"
          >
            Set up 2FA
          </button>
        )}
        {setup && (
          <div className="flex flex-col gap-3">
            <img
              src={setup.qr_data_uri}
              alt="TOTP setup QR code"
              className="h-44 w-44 rounded-sm border border-subtle bg-white"
            />
            <p className="text-xs text-tertiary">
              Secret: <code className="text-secondary">{setup.secret}</code>
            </p>
            <div className="flex gap-2">
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="6-digit code"
                className="h-9 w-40 rounded-sm border border-strong bg-inset px-2.5 text-sm"
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => void verifyTotp()}
                className="rounded-sm bg-accent-500 px-3 text-sm font-medium text-white"
              >
                Verify and enable
              </button>
            </div>
          </div>
        )}
        {me?.totp_enabled && (
          <p className="text-sm text-secondary">
            Two-factor is enabled. Recovery codes were shown once at setup; a
            fresh set can be issued through the API.
          </p>
        )}
      </section>

      <form
        onSubmit={changePassword}
        className="flex flex-col gap-3 rounded-sm border border-subtle bg-surface p-4"
      >
        <h2 className="text-sm font-semibold text-primary">Change password</h2>
        <input
          name="current"
          type="password"
          required
          placeholder="Current password"
          autoComplete="current-password"
          className="h-9 rounded-sm border border-strong bg-inset px-2.5 text-sm"
        />
        <input
          name="next"
          type="password"
          required
          minLength={8}
          placeholder="New password (8+ characters)"
          autoComplete="new-password"
          className="h-9 rounded-sm border border-strong bg-inset px-2.5 text-sm"
        />
        <input
          name="confirm"
          type="password"
          required
          placeholder="Confirm new password"
          autoComplete="new-password"
          className="h-9 rounded-sm border border-strong bg-inset px-2.5 text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="h-9 w-fit rounded-sm bg-accent-500 px-3 text-sm font-medium text-white"
        >
          Change password
        </button>
      </form>

      {note && <p className="text-sm text-secondary">{note}</p>}

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold text-primary">My recent activity</h2>
        {activity && activity.length === 0 && (
          <p className="text-sm text-secondary">No recorded activity yet.</p>
        )}
        <ul className="flex flex-col gap-1 text-sm text-secondary">
          {(activity ?? []).slice(0, 10).map((row, index) => (
            <li key={`${row.ts}-${index}`} className="flex justify-between gap-3">
              <span className="truncate">
                {formatEAT(row.ts)} · {row.action} · {row.summary}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
