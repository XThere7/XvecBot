"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ApiRequestError,
  apiGet,
  apiPost,
  resetUnauthorizedGuard,
} from "@/lib/api-client";
import { auth } from "@/lib/auth";

export type AdminMe = {
  id: string;
  email: string;
  role: "user" | "admin" | "superadmin";
  permissions: string[];
  totp_enabled: boolean;
};

/**
 * Obfuscated admin surface. The backend serves the same prefix
 * (settings.admin_route_prefix) and the frontend mirrors it here.
 */
export const ADMIN_HOME = "/bbx765adm";
export const ADMIN_LOGIN = `${ADMIN_HOME}/login`;

export type AdminSection = {
  href: string;
  label: string;
  permission?: string;
  superadminOnly?: boolean;
};

export const ADMIN_SECTIONS: AdminSection[] = [
  { href: ADMIN_HOME, label: "Overview", permission: "overview.read" },
  { href: `${ADMIN_HOME}/users`, label: "Users", permission: "users.read" },
  { href: `${ADMIN_HOME}/workspaces`, label: "Workspaces", permission: "workspaces.read" },
  { href: `${ADMIN_HOME}/knowledge`, label: "Knowledge", permission: "knowledge.read" },
  { href: `${ADMIN_HOME}/conversations`, label: "Conversations", permission: "analytics.read" },
  { href: `${ADMIN_HOME}/usage`, label: "Usage and Models", permission: "analytics.read" },
  { href: `${ADMIN_HOME}/subscriptions`, label: "Subscriptions", permission: "billing.read" },
  { href: `${ADMIN_HOME}/keys`, label: "API and Embeds", permission: "keys.manage" },
  { href: `${ADMIN_HOME}/system`, label: "System Health", permission: "system.read" },
  { href: `${ADMIN_HOME}/audit`, label: "Audit Log", permission: "audit.read" },
  { href: `${ADMIN_HOME}/admins`, label: "Admins", superadminOnly: true },
  { href: `${ADMIN_HOME}/platform`, label: "Platform Controls", superadminOnly: true },
  { href: `${ADMIN_HOME}/my-account`, label: "My Account" },
];

/** Current admin session (role/permissions re-read from the server). */
export function useAdminMe(): {
  me: AdminMe | null;
  loading: boolean;
  reload: () => void;
} {
  const [me, setMe] = React.useState<AdminMe | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    apiGet<AdminMe>("/auth/me", { skipAuthRedirect: true })
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch(() => {
        if (!cancelled) setMe(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { me, loading, reload: () => setTick((value) => value + 1) };
}

export function can(me: AdminMe | null, permission: string | undefined): boolean {
  if (!me) return false;
  if (me.role === "superadmin") return true;
  if (!permission) return true;
  return me.permissions.includes(permission);
}

export function isAdmin(me: AdminMe | null): boolean {
  return Boolean(me && (me.role === "admin" || me.role === "superadmin"));
}

/** UTC ISO → East Africa Time (Africa/Dar_es_Salaam) for display. */
export function formatEAT(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Africa/Dar_es_Salaam",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-GB").format(value);
}

export function formatTzs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `TZS ${new Intl.NumberFormat("en-GB").format(value)}`;
}

/** Generic paginated list fetch with search/sort/refresh state. */
export function useAdminList<T>(
  path: string,
  params: Record<string, string | number | undefined> = {},
) {
  const [items, setItems] = React.useState<T[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(25);
  const [search, setSearch] = React.useState("");
  const [sort, setSort] = React.useState<string>("");
  const [direction, setDirection] = React.useState<"asc" | "desc">("desc");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = React.useState<Date | null>(null);
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Panel API paths share the obfuscated admin prefix.
    const apiPath = path.startsWith("/") ? `${ADMIN_HOME}${path}` : path;
    const query = new URLSearchParams();
    query.set("page", String(page));
    query.set("page_size", String(pageSize));
    if (search.trim()) query.set("search", search.trim());
    if (sort) {
      query.set("sort", sort);
      query.set("direction", direction);
    }
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    apiGet<{ items: T[]; total: number }>(`${apiPath}?${query.toString()}`, {
      skipAuthRedirect: true,
    })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items ?? []);
        setTotal(data.total ?? 0);
        setUpdatedAt(new Date());
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const status = (err as { status?: number })?.status;
          setError(status === 403 ? "You do not have permission to view this." : "Could not load data.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, page, pageSize, search, sort, direction, tick, JSON.stringify(params)]);

  return {
    items,
    total,
    page,
    pageSize,
    search,
    sort,
    direction,
    loading,
    error,
    updatedAt,
    setPage,
    setPageSize,
    setSearch,
    setSort,
    setDirection,
    refresh: () => setTick((value) => value + 1),
  };
}

export type AdminLoginState = {
  pending: boolean;
  formError: string | null;
  /** Present when the account has 2FA enabled — the next step is a code. */
  totpToken: string | null;
  login: (email: string, password: string) => Promise<void>;
  completeTotp: (code: string) => Promise<void>;
  reset: () => void;
};

/**
 * Admin sign-in: same /auth endpoints as customers, but this form never
 * offers password recovery — admins are reset by the master admin instead.
 */
export function useAdminLogin(): AdminLoginState {
  const router = useRouter();
  const [pending, setPending] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [totpToken, setTotpToken] = React.useState<string | null>(null);

  const startSession = (token: string, userId: string, email: string) => {
    resetUnauthorizedGuard();
    auth.set(token, { userId, email });
  };

  const login = React.useCallback(
    async (email: string, password: string) => {
      setPending(true);
      setFormError(null);
      setTotpToken(null);
      try {
        const response = await apiPost<
          | { access_token: string; user_id: string }
          | { token_type: string; totp_token: string; user_id: string }
        >("/auth/login", { email, password }, { skipAuthRedirect: true });
        if ("totp_token" in response && response.totp_token) {
          setTotpToken(response.totp_token);
        } else if ("access_token" in response) {
          startSession(response.access_token, response.user_id, email);
          router.replace(ADMIN_HOME);
        }
      } catch (error) {
        if (error instanceof ApiRequestError) {
          setFormError(
            error.status === 401
              ? "Invalid email or password."
              : error.status === 429
                ? "Too many sign-in attempts. Try again later."
                : "Could not reach the server.",
          );
        } else {
          setFormError("Could not reach the server.");
        }
      } finally {
        setPending(false);
      }
    },
    [router],
  );

  const completeTotp = React.useCallback(
    async (code: string) => {
      if (!totpToken) return;
      setPending(true);
      setFormError(null);
      try {
        const response = await apiPost<{ access_token: string; user_id: string }>(
          "/auth/login/totp",
          { totp_token: totpToken, code },
          { skipAuthRedirect: true },
        );
        startSession(response.access_token, response.user_id, "");
        router.replace(ADMIN_HOME);
      } catch (error) {
        if (error instanceof ApiRequestError) {
          setFormError(
            error.status === 401
              ? "Invalid verification code."
              : error.status === 429
                ? "Too many attempts. Try again later."
                : "Could not reach the server.",
          );
        } else {
          setFormError("Could not reach the server.");
        }
      } finally {
        setPending(false);
      }
    },
    [totpToken, router],
  );

  const reset = React.useCallback(() => {
    setTotpToken(null);
    setFormError(null);
  }, []);

  return { pending, formError, totpToken, login, completeTotp, reset };
}
