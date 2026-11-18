"use client";

import * as React from "react";
import { apiGet, apiPost } from "@/lib/api-client";
import { ADMIN_HOME, formatEAT, useAdminMe } from "@/lib/admin";

type AdminRow = {
  id: string;
  email: string;
  role: string;
  permissions: string[];
  last_login_at: string | null;
  suspended_at: string | null;
  totp_enabled: number;
};

const PRESETS = ["support", "operations", "finance", "analyst"];

export default function AdminAdminsPage() {
  const { me } = useAdminMe();
  const [admins, setAdmins] = React.useState<AdminRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [email, setEmail] = React.useState("");
  const [preset, setPreset] = React.useState("support");
  const [busy, setBusy] = React.useState(false);
  const [note, setNote] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    apiGet<{ items: AdminRow[] }>(`${ADMIN_HOME}/admins`, { skipAuthRedirect: true })
      .then((data) => setAdmins(data.items))
      .catch(() => setError("Could not load admins."));
  }, []);

  React.useEffect(load, [load]);

  async function createAdmin() {
    if (!email.trim()) return;
    const password = window.prompt("Your password to confirm:") || "";
    if (!password) return;
    const code = window.prompt(
      "Your 6-digit 2FA code (leave blank if 2FA is not enabled):",
    ) || "";
    setBusy(true);
    setNote(null);
    try {
      await apiPost(
        `${ADMIN_HOME}/admins`,
        {
          email: email.trim(),
          preset,
          reauth_password: password,
          reauth_code: code,
        },
        { skipAuthRedirect: true },
      );
      setEmail("");
      load();
    } catch (err) {
      const status = (err as { status?: number })?.status;
      setNote(status === 403 ? "Re-authentication failed." : "Could not create the admin.");
    } finally {
      setBusy(false);
    }
  }

  async function suspendAdmin(admin: AdminRow) {
    const reason = window.prompt(`Suspend reason for ${admin.email}:`) || "no reason";
    await apiPost(
      `${ADMIN_HOME}/admins/${admin.id}/suspend`,
      { reason },
      { skipAuthRedirect: true },
    );
    load();
  }

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!admins) return <p className="text-sm text-secondary">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void createAdmin();
        }}
        className="flex flex-wrap items-end gap-2 rounded-sm border border-subtle bg-surface p-4"
      >
        <label className="flex flex-col gap-1 text-xs text-tertiary">
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            className="h-9 w-64 rounded-sm border border-strong bg-inset px-2.5 text-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-tertiary">
          Preset
          <select
            value={preset}
            onChange={(event) => setPreset(event.target.value)}
            className="h-9 rounded-sm border border-strong bg-inset px-2 text-sm text-primary"
          >
            {PRESETS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={busy}
          className="h-9 rounded-sm bg-accent-500 px-3 text-sm font-medium text-white disabled:opacity-50"
        >
          Create admin
        </button>
        {note && <p className="text-sm text-secondary">{note}</p>}
      </form>

      <table className="w-full overflow-hidden rounded-sm border border-subtle text-left text-sm">
        <thead>
          <tr className="bg-inset text-xs text-tertiary">
            <th className="px-3 py-2 font-medium">Email</th>
            <th className="px-3 py-2 font-medium">Role</th>
            <th className="px-3 py-2 font-medium">Permissions</th>
            <th className="px-3 py-2 font-medium">2FA</th>
            <th className="px-3 py-2 font-medium">Last login</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {admins.map((admin) => (
            <tr key={admin.id} className="border-t border-subtle">
              <td className="px-3 py-2 text-secondary">{admin.email}</td>
              <td className="px-3 py-2 text-secondary">{admin.role}</td>
              <td className="px-3 py-2 text-xs text-tertiary">
                {admin.role === "superadmin"
                  ? "all"
                  : admin.permissions.join(", ") || "none"}
              </td>
              <td className="px-3 py-2 text-secondary">
                {admin.totp_enabled ? "on" : "off"}
              </td>
              <td className="px-3 py-2 text-secondary">{formatEAT(admin.last_login_at)}</td>
              <td className="px-3 py-2">
                {admin.suspended_at ? (
                  <span className="text-danger-400">Suspended</span>
                ) : (
                  <span className="text-secondary">Active</span>
                )}
              </td>
              <td className="px-3 py-2">
                {admin.role !== "superadmin" && !admin.suspended_at && (
                  <button
                    type="button"
                    onClick={() => void suspendAdmin(admin)}
                    className="text-xs text-danger-400 hover:underline"
                  >
                    Suspend
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-tertiary">
        Only the bootstrap CLI can assign the superadmin role. {me?.email} is
        you.
      </p>
    </div>
  );
}
