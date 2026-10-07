import { auth } from "./auth";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(
  /\/+$/,
  "",
);

export class ApiRequestError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super("api");
    this.name = "ApiRequestError";
    this.status = status;
    this.body = body;
  }
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registered once by <SessionBoundary/> so the redirect survives a hard navigation. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

/** Reset by the auth pages so a fresh sign-in is never swallowed by the dedupe flag. */
export function resetUnauthorizedGuard() {
  handling401 = false;
}

// Module-level dedupe flag: concurrent 401s must produce one toast, one redirect.
let handling401 = false;

function handle401() {
  if (handling401) return;
  handling401 = true;
  auth.clear();
  unauthorizedHandler?.();
}

export type ApiOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | null;
  /** Skip the automatic 401 flow (used by /auth/login and /auth/register). */
  skipAuthRedirect?: boolean;
};

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { body, skipAuthRedirect, headers, ...rest } = opts;

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const hasJsonBody = body !== undefined && body !== null && !isFormData;

  let payload: BodyInit | undefined;
  if (hasJsonBody) {
    payload = JSON.stringify(body);
  } else if (isFormData) {
    payload = body as FormData;
  }

  const token = auth.get();

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      body: payload,
      headers: {
        // Never set Content-Type for FormData — it must keep its boundary.
        ...(hasJsonBody ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...((headers as Record<string, string>) ?? {}),
      },
    });
  } catch {
    throw new ApiRequestError(0, { detail: "Cannot reach the server." });
  }

  if (res.status === 401 && !skipAuthRedirect) {
    handle401();
  }

  if (res.status === 204) return undefined as T;

  const parsed = (await res.json().catch(() => ({}))) as T;

  if (!res.ok) {
    throw new ApiRequestError(res.status, parsed);
  }

  return parsed;
}

export const apiGet = <T>(path: string, init?: Omit<ApiOptions, "method" | "body">) =>
  api<T>(path, { ...init, method: "GET" });

export const apiPost = <T>(
  path: string,
  body?: ApiOptions["body"],
  init?: Omit<ApiOptions, "method" | "body">,
) => api<T>(path, { ...init, method: "POST", body });

export const apiPut = <T>(
  path: string,
  body?: ApiOptions["body"],
  init?: Omit<ApiOptions, "method" | "body">,
) => api<T>(path, { ...init, method: "PUT", body });

export const apiDelete = <T>(path: string, init?: Omit<ApiOptions, "method" | "body">) =>
  api<T>(path, { ...init, method: "DELETE" });