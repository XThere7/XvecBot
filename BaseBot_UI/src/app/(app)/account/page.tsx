"use client";

import * as React from "react";
import { LogOut, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { DefinitionList } from "@/components/ui/definition-list";
import { APP_NAME, SITE_URL } from "@/lib/constants";
import { API_BASE_URL } from "@/lib/api-client";
import { formatAbsoluteTime } from "@/lib/format";
import { useLogout, useSessionExpiry } from "@/hooks/use-auth";
import { useSession } from "@/stores/session";

export default function AccountPage() {
  const user = useSession((state) => state.user);
  const token = useSession((state) => state.token);
  const logout = useLogout();
  const expiry = useSessionExpiry();

  if (!token) {
    return (
      <div className="flex flex-col gap-8">
        <PageHeader title="Account" description="You are signed out." />
        <AlertBanner tone="info" title="Signed out">
          There is no profile-editing endpoint in this product. Sign in again to
          manage your workspaces.
        </AlertBanner>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Account"
        description="Your session lives in memory only — there is nothing stored in this browser."
        actions={
          <Button
            variant="danger"
            iconLeft={<LogOut aria-hidden className="h-4 w-4" />}
            onClick={logout}
          >
            Log out
          </Button>
        }
      />

      <section className="rounded-md border border-subtle bg-surface p-6 shadow-elevation-1">
        <h2 className="text-xl text-primary">Profile</h2>
        <DefinitionList
          className="mt-5"
          columns={1}
          items={[
            { label: "Email", value: user?.email ?? "—" },
            {
              label: "User ID",
              value: user?.userId ?? "—",
              mono: true,
            },
            {
              label: "Signed in until",
              // The JWT has no `iat` and there is no refresh token, so nothing
              // more precise than the expiry claim can be shown.
              value: expiry ? formatAbsoluteTime(expiry.toISOString()) : "Unknown",
              note: "Taken from the token's exp claim. The token is not renewed automatically.",
            },
            { label: "Product", value: APP_NAME },
          ]}
        />
      </section>

      <section className="rounded-md border border-subtle bg-surface p-6">
        <h2 className="flex items-center gap-2 text-xl text-primary">
          <ShieldCheck aria-hidden className="h-5 w-5 text-tertiary" />
          Session &amp; API
        </h2>
        <DefinitionList
          className="mt-5"
          columns={1}
          items={[
            { label: "API base URL", value: API_BASE_URL, mono: true },
            { label: "Dashboard URL", value: SITE_URL || "—", mono: true },
            {
              label: "Token storage",
              value: "In memory only (never localStorage, sessionStorage or a cookie)",
              note: "A hard refresh signs you out. That is a deliberate trade-off for a dashboard holding merchant data.",
            },
            {
              label: "Session lifetime",
              value: "7 days",
              note: "There is no refresh token. You re-authenticate when it expires.",
            },
          ]}
        />
      </section>

      <section className="rounded-md border border-subtle bg-surface p-6">
        <h2 className="text-xl text-primary">Danger zone</h2>
        <p className="mt-1.5 max-w-2xl text-sm leading-5 text-secondary">
          Logging out clears the token from memory immediately. Every request
          after that is unauthenticated.
        </p>
        <div className="mt-4 flex justify-end">
          <Button variant="danger" onClick={logout} iconLeft={<LogOut aria-hidden className="h-4 w-4" />}>
            Log out
          </Button>
        </div>
      </section>
    </div>
  );
}