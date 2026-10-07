import { useSession, type SessionUser } from "@/stores/session";

/**
 * In-memory session accessor. The JWT lives in a module-level store and is
 * never persisted — see frontendbot.md §6.2.
 */
export const auth = {
  get: (): string | null => useSession.getState().token,
  getUser: (): SessionUser | null => useSession.getState().user,
  set: (token: string, user: SessionUser) => useSession.getState().setSession(token, user),
  clear: () => useSession.getState().clearSession(),
};

/**
 * Decode `exp` for a friendlier account screen. The payload contains only
 * `sub` and `exp` (no `iat`), so nothing can be derived beyond the expiry.
 * Returns null for anything undecodable — callers must tolerate that.
 */
export function decodeTokenExpiry(token: string | null): Date | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as { exp?: number };
    if (typeof payload.exp !== "number") return null;
    return new Date(payload.exp * 1000);
  } catch {
    return null;
  }
}