import type { ErrorDetail, ErrorEnvelope, SuccessEnvelope } from "../contracts";

const API_ROOT = "/api/v1";

let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(options: {
    status: number;
    code: string;
    message: string;
    retryable: boolean;
    details: ErrorDetail[];
    requestId: string | null;
    retryAfterSeconds?: number | null;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable;
    this.details = options.details;
    this.requestId = options.requestId;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }
}

export function configureApiAuth(token: string | null, onUnauthorized: (() => void) | null): void {
  accessToken = token;
  unauthorizedHandler = onUnauthorized;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<SuccessEnvelope<T>> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers,
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "The Backend could not be reached. Check the connection and retry.",
      retryable: true,
      details: [],
      requestId: null,
    });
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = isErrorEnvelope(payload) ? payload : null;
    const retryAfter = response.headers.get("Retry-After");
    const parsedRetryAfter = retryAfter ? Number(retryAfter) : null;
    const error = new ApiError({
      status: response.status,
      code: envelope?.error.code ?? `HTTP_${response.status}`,
      message: envelope?.error.message ?? "The request failed without a valid error envelope.",
      retryable: envelope?.error.retryable ?? false,
      details: envelope?.error.details ?? [],
      requestId: envelope?.meta.requestId ?? response.headers.get("X-Request-ID"),
      retryAfterSeconds: Number.isFinite(parsedRetryAfter) ? parsedRetryAfter : null,
    });
    if (response.status === 401) unauthorizedHandler?.();
    throw error;
  }
  if (!isSuccessEnvelope<T>(payload)) {
    throw new ApiError({
      status: response.status,
      code: "INVALID_ENVELOPE",
      message: "The Backend returned an invalid success envelope.",
      retryable: false,
      details: [],
      requestId: response.headers.get("X-Request-ID"),
    });
  }
  return payload;
}

export function buildQuery(values: Record<string, string | number | readonly number[] | undefined | null>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) query.append(key, String(item));
    } else {
      query.set(key, String(value));
    }
  }
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

function isSuccessEnvelope<T>(payload: unknown): payload is SuccessEnvelope<T> {
  if (!isRecord(payload) || !("data" in payload) || !isRecord(payload.meta)) return false;
  return typeof payload.meta.requestId === "string";
}

function isErrorEnvelope(payload: unknown): payload is ErrorEnvelope {
  if (!isRecord(payload) || !isRecord(payload.error) || !isRecord(payload.meta)) return false;
  return (
    typeof payload.error.code === "string" &&
    typeof payload.error.message === "string" &&
    typeof payload.error.retryable === "boolean" &&
    Array.isArray(payload.error.details) &&
    typeof payload.meta.requestId === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
