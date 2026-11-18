"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { apiGet, apiPost, api } from "@/lib/api-client";
import { formatEAT } from "@/lib/admin";
import { ADMIN_HOME, useAdminMe } from "@/lib/admin";

type UserDetail = {
  id: string;
  email: string;
  role: string;
  plan: string;
  trial_ends_at: string | null;
  last_login_at: string | null;
  suspended_at: string | null;
  suspended_reason: string | null;
  created_at: string;
  workspace_count: number;
  agent_count: number;
  api_keys: Record<string, unknown>[];
  embed_tokens: Record<string, unknown>[];
};

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const { me } = useAdminMe();
  const [user, setUser] = React.useState<UserDetail | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(() => {
    apiGet<UserDetail>(`${ADMIN_HOME}/users/${params.id}`, { skipAuthRedirect: true })
      .then(setUser)
      .catch(() => setError("Could not load this user."));
  }, [params.id]);

  React.useEffect(load, [load]);

  async function act(
    action: () => Promise<unknown>,
    confirmMessage?: string,
  ): Promise<void> {
    if (confirmMessage && !window.confirm(confirmMessage)) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      const detail = (err as { body?: { detail?: string } })?.body?.detail;
      setError(detail ?? "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!user) return <p className="text-sm text-secondary">Loading…</p>;

  const isSuper = me?.role === "superadmin";

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg text-primary">{user.email}</h2>
      <dl className="grid max-w-2xl grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <dt className="text-tertiary">Role</dt>
        <dd className="text-secondary">{user.role}</dd>
        <dt className="text-tertiary">Plan</dt>
        <dd className="text-secondary">{user.plan}</dd>
        <dt className="text-tertiary">Trial ends</dt>
        <dd className="text-secondary">{formatEAT(user.trial_ends_at)}</dd>
        <dt className="text-tertiary">Last login</dt>
        <dd className="text-secondary">{formatEAT(user.last_login_at)}</dd>
        <dt className="text-tertiary">Joined</dt>
        <dd className="text-secondary">{formatEAT(user.created_at)}</dd>
        <dt className="text-tertiary">Workspaces / Agents</dt>
        <dd className="text-secondary">
          {user.workspace_count} / {user.agent_count}
        </dd>
        <dt className="text-tertiary">API keys / Embed tokens</dt>
        <dd className="text-secondary">
          {user.api_keys.length} / {user.embed_tokens.length}
        </dd>
        {user.suspended_at && (
          <>
            <dt className="text-tertiary">Suspended</dt>
            <dd className="text-danger-400">
              {formatEAT(user.suspended_at)} — {user.suspended_reason ?? "no reason"}
            </dd>
          </>
        )}
      </dl>

      <div className="flex flex-wrap gap-2">
        {user.suspended_at ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => act(() => apiPost(`${ADMIN_HOME}/users/${user.id}/reactivate`, {}, { skipAuthRedirect: true }))}
            className="rounded-sm bg-accent-500 px-3 py-2 text-sm font-medium text-white"
          >
            Reactivate
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              act(
                () =>
                  apiPost(
                    `${ADMIN_HOME}/users/${user.id}/suspend`,
                    { reason: window.prompt("Suspension reason:") || "no reason" },
                    { skipAuthRedirect: true },
                  ),
                "Suspend this account?",
              )
            }
            className="rounded-sm bg-danger-500 px-3 py-2 text-sm font-medium text-white"
          >
            Suspend
          </button>
        )}

        <button
          type="button"
          disabled={busy}
          onClick={() =>
            act(() =>
              apiPost(
                `${ADMIN_HOME}/users/${user.id}/plan`,
                {
                  plan: window.prompt("New plan (free/standard/pro):") || "free",
                  reason: window.prompt("Reason:") || "admin change",
                },
                { skipAuthRedirect: true },
              ),
            )
          }
          className="rounded-sm border border-subtle px-3 py-2 text-sm text-secondary"
        >
          Change plan
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() =>
            act(() =>
              apiPost(
                `${ADMIN_HOME}/users/${user.id}/trial`,
                { days: Number(window.prompt("Trial days (0 ends, e.g. 30):") || "0"), reason: "admin change" },
                { skipAuthRedirect: true },
              ),
            )
          }
          className="rounded-sm border border-subtle px-3 py-2 text-sm text-secondary"
        >
          Adjust trial
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => apiPost(`${ADMIN_HOME}/users/${user.id}/send-reset`, {}, { skipAuthRedirect: true }))}
          className="rounded-sm border border-subtle px-3 py-2 text-sm text-secondary"
        >
          Send reset email
        </button>

        {isSuper && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              act(
                () =>
                  api(`${ADMIN_HOME}/users/${user.id}`, {
                    method: "DELETE",
                    body: {
                      email_confirmation: window.prompt(
                        `Type the email to permanently delete:\n${user.email}`,
                      ) || "",
                      reauth_password: window.prompt("Your password to confirm:") || "",
                      reauth_code: window.prompt(
                        "Your 6-digit 2FA code (leave blank if 2FA is not enabled):",
                      ) || "",
                    },
                    skipAuthRedirect: true,
                  }),
                "Permanently delete this user and all their data?",
              )
            }
            className="rounded-sm border border-danger-500 px-3 py-2 text-sm font-medium text-danger-400"
          >
            Delete permanently
          </button>
        )}
      </div>
    </div>
  );
}
