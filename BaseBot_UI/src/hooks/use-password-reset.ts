"use client";

import * as React from "react";
import { ApiRequestError, apiGet, apiPost } from "@/lib/api-client";
import { normaliseError, type FieldIssue } from "@/lib/api-error";

export const RESET_LINK_INVALID = "This reset link is invalid or has expired.";

export type ForgotPasswordState = {
  pending: boolean;
  /** True once the neutral confirmation should be shown. */
  sent: boolean;
  /** True when the server said 429 — show a calm "try again later" note. */
  rateLimited: boolean;
  formError: string | null;
};

export function useForgotPassword() {
  const [state, setState] = React.useState<ForgotPasswordState>({
    pending: false,
    sent: false,
    rateLimited: false,
    formError: null,
  });

  const submit = React.useCallback(async (email: string) => {
    setState({ pending: true, sent: false, rateLimited: false, formError: null });
    try {
      // The API answers 200 with the neutral body for every address, so this
      // call never reveals whether an account exists.
      await apiPost("/auth/forgot-password", { email }, { skipAuthRedirect: true });
      setState({ pending: false, sent: true, rateLimited: false, formError: null });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 429) {
        setState({ pending: false, sent: true, rateLimited: true, formError: null });
      } else if (error instanceof ApiRequestError && error.status === 0) {
        setState({ pending: false, sent: false, rateLimited: false, formError: "Cannot reach the server." });
      } else {
        // Any other outcome still shows the neutral confirmation — no
        // account-existence hint may leak.
        setState({ pending: false, sent: true, rateLimited: false, formError: null });
      }
    }
  }, []);

  return { ...state, submit };
}

export type ResetStatus = "loading" | "invalid" | "ready" | "success";

export type ResetPasswordState = {
  status: ResetStatus;
  pending: boolean;
  formError: string | null;
  fieldErrors: FieldIssue[];
  submit: (newPassword: string, confirmPassword: string) => Promise<boolean>;
};

export function useResetPassword(token: string | null): ResetPasswordState {
  const [status, setStatus] = React.useState<ResetStatus>("loading");
  const [pending, setPending] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<FieldIssue[]>([]);
  const tokenRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!token) {
      setStatus("invalid");
      return;
    }
    // Take the token out of the address bar (and out of the referrer, which is
    // also protected by Referrer-Policy: no-referrer on this page).
    if (typeof window !== "undefined" && window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    let cancelled = false;
    apiGet<{ valid: boolean }>(
      `/auth/reset-password/validate?token=${encodeURIComponent(token)}`,
      { skipAuthRedirect: true },
    )
      .then((result) => {
        if (cancelled) return;
        if (result.valid) {
          tokenRef.current = token;
          setStatus("ready");
        } else {
          setStatus("invalid");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("invalid");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const submit = React.useCallback(
    async (newPassword: string, confirmPassword: string): Promise<boolean> => {
      if (!tokenRef.current) {
        setStatus("invalid");
        return false;
      }
      setPending(true);
      setFormError(null);
      setFieldErrors([]);
      try {
        await apiPost(
          "/auth/reset-password",
          {
            token: tokenRef.current,
            new_password: newPassword,
            confirm_password: confirmPassword,
          },
          { skipAuthRedirect: true },
        );
        tokenRef.current = null;
        setStatus("success");
        return true;
      } catch (error) {
        if (error instanceof ApiRequestError) {
          const detail = (error.body as { detail?: unknown } | null)?.detail;
          if (detail === RESET_LINK_INVALID) {
            tokenRef.current = null;
            setStatus("invalid");
            return false;
          }
          if (detail === "New passwords do not match.") {
            setFormError("The passwords you entered do not match.");
            return false;
          }
          const normalised = normaliseError(error.body, error.status);
          if (normalised.fieldErrors.length > 0) {
            setFieldErrors(normalised.fieldErrors);
          } else {
            setFormError(normalised.message);
          }
        } else {
          setFormError("Cannot reach the server.");
        }
        return false;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  return { status, pending, formError, fieldErrors, submit };
}
