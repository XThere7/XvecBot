export type FieldIssue = { field: string; message: string };

export type NormalisedError = {
  message: string;
  fieldErrors: FieldIssue[];
};

/**
 * `detail` is polymorphic on this API:
 *   string → 400 / 401 / 403 / 404 / 409 / 500
 *   array  → 422 validation, shaped [{ type, loc, msg }]
 *   object → rare, treated generically
 */
export function normaliseError(
  body: unknown,
  status: number,
): NormalisedError {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (Array.isArray(detail)) {
    const fieldErrors: FieldIssue[] = detail.map((d) => {
      const loc = (d as { loc?: unknown }).loc;
      return {
        field: Array.isArray(loc) && loc.length > 0
          ? String(loc[loc.length - 1])
          : "form",
        message: String((d as { msg?: string }).msg ?? "Invalid value"),
      };
    });
    return { message: "Please check the highlighted fields.", fieldErrors };
  }

  if (typeof detail === "string") {
    return { message: friendlyMessage(detail, status), fieldErrors: [] };
  }

  if (typeof detail === "object" && detail !== null) {
    const errors = (detail as { errors?: Record<string, string> }).errors;
    if (errors && typeof errors === "object") {
      return {
        message: "Please check the highlighted fields.",
        fieldErrors: Object.entries(errors).map(([field, message]) => ({
          field,
          message: String(message),
        })),
      };
    }
  }

  if (status === 401) {
    return {
      message: "Your session has expired. Please sign in again.",
      fieldErrors: [],
    };
  }

  if (status === 403) {
    return { message: "You don't have access to this resource.", fieldErrors: [] };
  }

  if (status === 429) {
    return { message: "You're sending messages too fast.", fieldErrors: [] };
  }

  if (status === 0) {
    return { message: "Cannot reach the server.", fieldErrors: [] };
  }

  return { message: "Something went wrong. Please try again.", fieldErrors: [] };
}

/**
 * Known backend messages → copy a non-technical owner can act on.
 * Anything unrecognised falls back to generic copy.
 */
const KNOWN_MESSAGES: Record<string, string> = {
  "Email already registered": "That email is already registered.",
  "Invalid credentials": "Invalid email or password.",
  "Invalid or expired token": "Your session has expired. Please sign in again.",
  "Workspace not found": "Workspace not found.",
  "Agent not found": "Agent not found.",
  "Conversation not found": "Conversation not found.",
  "Agent is not available.": "This agent is inactive.",
  "Rate limit exceeded. Please slow down.": "You're sending messages too fast.",
};

const COPY_BY_STATUS: Record<number, string> = {
  400: "Something went wrong. Please try again.",
  401: "Your session has expired. Please sign in again.",
  403: "You don't have access to this resource.",
  404: "We couldn't find that.",
  409: "Something went wrong. Please try again.",
  500: "Something went wrong. Please try again.",
};

export function friendlyMessage(detail: string, status: number): string {
  const known = KNOWN_MESSAGES[detail];
  if (known) return known;

  // `Unsupported file type '.exe'. Allowed: .pdf, .txt, .docx` — shown verbatim.
  if (detail.startsWith("Unsupported file type")) return detail;

  if (status === 401) return "Your session has expired. Please sign in again.";
  return COPY_BY_STATUS[status] ?? "Something went wrong. Please try again.";
}