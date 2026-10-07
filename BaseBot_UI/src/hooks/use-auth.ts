"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ApiRequestError,
  apiPost,
  resetUnauthorizedGuard,
  setUnauthorizedHandler,
} from "@/lib/api-client";
import { normaliseError, type FieldIssue } from "@/lib/api-error";
import { auth, decodeTokenExpiry } from "@/lib/auth";
import { SESSION_EXPIRED_MESSAGE, TOAST_DURATION } from "@/lib/constants";
import { useSession } from "@/stores/session";
import { tokenResponseSchema } from "@/schemas/auth";
import type { TokenResponse } from "@/types/api";

export type AuthFormState = {
  fieldErrors: FieldIssue[];
  formError: string | null;
  pending: boolean;
  setPending: (pending: boolean) => void;
  setFieldErrors: (errors: FieldIssue[]) => void;
  setFormError: (message: string | null) => void;
};

export function useAuthFormState(): AuthFormState {
  const [fieldErrors, setFieldErrors] = React.useState<FieldIssue[]>([]);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  return {
    fieldErrors,
    formError,
    pending,
    setPending,
    setFieldErrors,
    setFormError,
  };
}

export function fieldErrorFor(errors: FieldIssue[], field: string): string | undefined {
  return errors.find((e) => e.field === field)?.message;
}

function useStartSession() {
  const queryClient = useQueryClient();
  return React.useCallback(
    (token: string, userId: string, email: string) => {
      resetUnauthorizedGuard();
      auth.set(token, { userId, email });
      queryClient.clear();
    },
    [queryClient],
  );
}

async function authenticate(
  path: "/auth/login" | "/auth/register",
  email: string,
  password: string,
): Promise<{ token: string; userId: string }> {
  const response = await apiPost<TokenResponse>(
    path,
    { email, password },
    { skipAuthRedirect: true },
  );
  const parsed = tokenResponseSchema.parse(response);
  return { token: parsed.access_token, userId: parsed.user_id };
}

export function useLogin() {
  const router = useRouter();
  const startSession = useStartSession();
  const state = useAuthFormState();

  const login = React.useCallback(
    async (email: string, password: string, redirectTo?: string | null) => {
      state.setFormError(null);
      state.setFieldErrors([]);
      state.setPending(true);
      try {
        const parsed = await authenticate("/auth/login", email, password);
        startSession(parsed.token, parsed.userId, email);
        router.replace(
          redirectTo && redirectTo.startsWith("/") ? redirectTo : "/dashboard",
        );
        return true;
      } catch (error) {
        if (error instanceof ApiRequestError) {
          const normalised = normaliseError(error.body, error.status);
          if (normalised.fieldErrors.length > 0) {
            state.setFieldErrors(normalised.fieldErrors);
          } else {
            state.setFormError(
              error.status === 401
                ? "Invalid email or password."
                : normalised.message,
            );
          }
        } else {
          state.setFormError("Cannot reach the server.");
        }
        return false;
      } finally {
        state.setPending(false);
      }
    },
    [router, startSession, state],
  );

  return { ...state, login };
}

export function useRegister() {
  const router = useRouter();
  const startSession = useStartSession();
  const state = useAuthFormState();

  const register = React.useCallback(
    async (email: string, password: string) => {
      state.setFormError(null);
      state.setFieldErrors([]);
      state.setPending(true);
      try {
        const parsed = await authenticate("/auth/register", email, password);
        startSession(parsed.token, parsed.userId, email);
        router.replace("/dashboard");
        return true;
      } catch (error) {
        if (error instanceof ApiRequestError) {
          const normalised = normaliseError(error.body, error.status);
          if (normalised.fieldErrors.length > 0) {
            state.setFieldErrors(normalised.fieldErrors);
          } else {
            state.setFormError(normalised.message);
          }
        } else {
          state.setFormError("Cannot reach the server.");
        }
        return false;
      } finally {
        state.setPending(false);
      }
    },
    [router, startSession, state],
  );

  return { ...state, register };
}

/**
 * Sends an authenticated user away from /login and /register. Renders nothing
 * until the in-memory token is known, so a protected page never flashes.
 */
export function useSessionBoundary() {
  const router = useRouter();
  const pathname = usePathname();
  const token = useSession((state) => state.token);
  const [resolved, setResolved] = React.useState(false);

  React.useEffect(() => {
    if (token) {
      setResolved(true);
      if (pathname === "/login" || pathname === "/register") {
        router.replace("/dashboard");
      }
      return;
    }
    setResolved(true);
  }, [token, pathname, router]);

  return { token, resolved };
}

/** Sends an unauthenticated visitor to /login with a ?redirect= back-link. */
export function useAuthGuard() {
  const router = useRouter();
  const pathname = usePathname();
  const token = useSession((state) => state.token);
  const [redirected, setRedirected] = React.useState(false);

  React.useEffect(() => {
    if (token) return;
    // Read the query string off `window` rather than through a hook so the app
    // shell never suspends and the guard resolves on the first client tick.
    const search = typeof window === "undefined" ? "" : window.location.search;
    const target = `${pathname}${search}`;
    setRedirected(true);
    router.replace(`/login?redirect=${encodeURIComponent(target)}`);
  }, [token, pathname, router]);

  return { authenticated: Boolean(token), redirected };
}

/**
 * Wires the api client's single 401 handler: clear token, one warning toast,
 * then replace to /login preserving the current location.
 */
export function useUnauthorizedHandler() {
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    setUnauthorizedHandler(() => {
      const search = typeof window === "undefined" ? "" : window.location.search;
      const target = `${pathname}${search}`;
      toast.warning(SESSION_EXPIRED_MESSAGE, {
        duration: TOAST_DURATION.warning,
        id: "session-expired",
      });
      router.replace(`/login?redirect=${encodeURIComponent(target)}`);
    });
    return () => setUnauthorizedHandler(null);
  }, [pathname, router]);
}

export function useLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return React.useCallback(() => {
    auth.clear();
    queryClient.clear();
    router.replace("/login");
  }, [router, queryClient]);
}

export function useSessionExpiry(): Date | null {
  const token = useSession((state) => state.token);
  return React.useMemo(() => decodeTokenExpiry(token), [token]);
}