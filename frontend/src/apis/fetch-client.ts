/**
 * Shared fetch mutator for every Orval-generated React Query hook.
 *
 * It deliberately uses relative URLs so the Vite proxy handles development and
 * the production container can serve the API from the same origin. Responses
 * that are not 2xx become an ApiError carrying FastAPI's stable error code and
 * human-readable detail.
 */
import { getActiveLocale, translate } from "../app/i18n/translate";

const JSON_TYPE = "application/json";

interface ErrorRecord {
  [key: string]: unknown;
}

/** An HTTP failure with enough structure for a page-level error state. */
export class ApiError extends Error {
  readonly status: number;

  readonly code: string;

  readonly detail: string;

  readonly payload: unknown;

  constructor(status: number, code: string, detail: string, payload: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.payload = payload;
  }
}

function isRecord(value: unknown): value is ErrorRecord {
  return typeof value === "object" && value !== null;
}

function textFromDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }
  if (!Array.isArray(detail)) {
    return null;
  }
  const messages = detail.flatMap((item) => {
    if (!isRecord(item) || typeof item.msg !== "string") {
      return [];
    }
    return [item.msg];
  });
  return messages.length > 0 ? messages.join("; ") : null;
}

function messageFromPayload(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }
  if (!isRecord(payload)) {
    return fallback;
  }
  const detail = textFromDetail(payload.detail);
  if (detail) {
    return detail;
  }
  if (typeof payload.error === "string" && payload.error.trim().length > 0) {
    return payload.error;
  }
  return fallback;
}

function codeFromPayload(payload: unknown): string {
  if (isRecord(payload) && typeof payload.error === "string" && payload.error.length > 0) {
    return payload.error;
  }
  return "http_error";
}

async function parseResponsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes(JSON_TYPE)) {
    try {
      return (await response.json()) as unknown;
    } catch {
      return null;
    }
  }
  const text = await response.text();
  return text.length > 0 ? text : null;
}

/**
 * Fetches a relative API path and resolves the parsed payload.
 *
 * @template T - The shape the generated hook expects for a successful response.
 * @param url - Relative API path, for example `/api/v1/search?query=rings`.
 * @param options - Standard request options; credentials default to same-origin.
 * @returns The parsed JSON payload, or undefined for a 204 response.
 * @throws {ApiError} When the response status is outside the 2xx range.
 */
export async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", JSON_TYPE);
  }
  const isFormData = options.body instanceof FormData;
  if (options.body != null && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", JSON_TYPE);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      credentials: options.credentials ?? "same-origin",
    });
  } catch (error) {
    const message =
      error instanceof Error && error.message.trim().length > 0
        ? error.message
        : translate(getActiveLocale(), "core.errors.network_error");
    throw new ApiError(0, "network_error", message, null);
  }

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("apsor-archive:unauthorized"));
    }
    const payload = await parseResponsePayload(response);
    throw new ApiError(
      response.status,
      codeFromPayload(payload),
      messageFromPayload(
        payload,
        response.statusText ||
          translate(getActiveLocale(), "core.errors.generic"),
      ),
      payload,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await parseResponsePayload(response)) as T;
}
