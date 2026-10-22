import {
  publicAgentInfoSchema,
  publicChatResponseSchema,
} from "@/schemas/chat";
import type { PublicAgentInfo, PublicChatResponse } from "@/types/api";

/** Public calls deliberately bypass the dashboard api-client: no JWT, no 401 redirect. */
export const PUBLIC_API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? ""
).replace(/\/+$/, "");

export class PublicApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "PublicApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function publicRequest<T>(
  path: string,
  init: RequestInit,
  parse: (value: unknown) => T,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${PUBLIC_API_BASE_URL}${path}`, {
      ...init,
      credentials: "omit",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new PublicApiError(
      0,
      "We could not reach the chat service. Check your connection and try again.",
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    let message =
      typeof detail === "string"
        ? detail
        : response.status === 429
          ? "Too many messages. Please wait a moment and try again."
          : "This chat is temporarily unavailable. Please try again.";
    if (response.status === 401 || response.status === 403 || response.status === 404) {
      message = "This chat link is invalid, expired, or has been disabled.";
    }
    throw new PublicApiError(response.status, message);
  }

  return parse(body);
}

export async function getPublicAgent(
  token: string,
  signal?: AbortSignal,
): Promise<PublicAgentInfo> {
  return publicRequest(
    `/public/agent/${encodeURIComponent(token)}`,
    { method: "GET", signal },
    (body) => publicAgentInfoSchema.parse(body),
  );
}

export async function sendPublicChat(
  token: string,
  message: string,
  conversationId: string | null,
): Promise<PublicChatResponse> {
  return publicRequest(
    "/public/chat",
    {
      method: "POST",
      body: JSON.stringify({
        token,
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
    },
    (body) => publicChatResponseSchema.parse(body),
  );
}
