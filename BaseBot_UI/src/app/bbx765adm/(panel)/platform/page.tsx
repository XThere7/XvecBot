"use client";

import * as React from "react";
import { apiGet, apiPut } from "@/lib/api-client";
import { ADMIN_HOME } from "@/lib/admin";

type PlatformSettings = {
  signups_open: boolean;
  maintenance_message: string;
  emergency_off: boolean;
};

export default function AdminPlatformPage() {
  const [settings, setSettings] = React.useState<PlatformSettings | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(() => {
    apiGet<PlatformSettings>(`${ADMIN_HOME}/platform/settings`, { skipAuthRedirect: true })
      .then(setSettings)
      .catch(() => setError("Could not load platform controls."));
  }, []);

  React.useEffect(load, [load]);

  async function save(patch: Partial<PlatformSettings>, reason: string) {
    const password = window.prompt("Your password to confirm:") || "";
    setBusy(true);
    setNote(null);
    try {
      await apiPut(
        `${ADMIN_HOME}/platform/settings`,
        { ...patch, reason, reauth_password: password },
        { skipAuthRedirect: true },
      );
      load();
    } catch (err) {
      const status = (err as { status?: number })?.status;
      setNote(status === 403 ? "Re-authentication failed." : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!settings) return <p className="text-sm text-secondary">Loading…</p>;

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <h2 className="text-lg text-primary">Platform controls</h2>
      <p className="text-sm text-secondary">
        Every change requires your password (and a 2FA code when enabled) and
        is written to the audit log.
      </p>

      <label className="flex items-center justify-between gap-3 rounded-sm border border-subtle bg-surface p-4">
        <span className="text-sm text-primary">New sign-ups open</span>
        <input
          type="checkbox"
          checked={settings.signups_open}
          disabled={busy}
          onChange={(event) =>
            void save({ signups_open: event.target.checked }, "signups toggle")
          }
          className="h-5 w-5 accent-[var(--color-accent-500)]"
        />
      </label>

      <label className="flex items-center justify-between gap-3 rounded-sm border border-danger-500/50 bg-surface p-4">
        <span className="text-sm text-primary">
          Emergency switch — stop widget, hosted pages and Developer API
        </span>
        <input
          type="checkbox"
          checked={settings.emergency_off}
          disabled={busy}
          onChange={(event) =>
            void save({ emergency_off: event.target.checked }, "emergency toggle")
          }
          className="h-5 w-5 accent-[var(--color-danger-500)]"
        />
      </label>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          const value = (event.target as HTMLFormElement).maintenance.value;
          void save({ maintenance_message: value }, "maintenance banner");
        }}
        className="flex flex-col gap-2 rounded-sm border border-subtle bg-surface p-4"
      >
        <label className="text-sm text-primary" htmlFor="maintenance-message">
          Maintenance banner
        </label>
        <input
          id="maintenance-message"
          name="maintenance"
          defaultValue={settings.maintenance_message}
          className="h-9 rounded-sm border border-strong bg-inset px-2.5 text-sm text-primary"
          placeholder="Leave empty for no banner"
        />
        <button
          type="submit"
          disabled={busy}
          className="h-9 w-fit rounded-sm bg-accent-500 px-3 text-sm font-medium text-white disabled:opacity-50"
        >
          Save banner
        </button>
      </form>

      {note && <p className="text-sm text-secondary">{note}</p>}
    </div>
  );
}
