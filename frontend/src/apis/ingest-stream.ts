/**
 * Streaming transport for durable ingestion progress.
 *
 * The generated client describes `GET /files/ingest-jobs/{id}/events` as a
 * JSON-ish query, so the browser uses this small fetch client instead: it asks
 * for `text/event-stream`, parses frames as they arrive, and never holds a
 * request database session open. The durable job row remains authoritative; a
 * stream error falls back to the existing polling helper in `library-utils`.
 */
import { ApiError } from "./fetch-client";
import { getActiveLocale, translate } from "../app/i18n/translate";
import type { IngestJobSchema } from "../app/generated-apis-types/schemas";

export const INGEST_EVENT_TYPES = ["snapshot", "progress"] as const;

export type IngestEventType = (typeof INGEST_EVENT_TYPES)[number];

/** One compact progress event; it never carries paths or archive content. */
export interface IngestProgressEvent {
  readonly id: number;
  readonly status: IngestJobSchema["status"];
  readonly stage: string | null;
  readonly progress_pct: number;
  readonly stage_done: number | null;
  readonly stage_total: number | null;
  readonly stage_unit: string | null;
  readonly chunks_total: number | null;
  readonly chunks_embedded: number | null;
  readonly file_id: number | null;
  readonly error_code: string | null;
  readonly error_detail: string | null;
  readonly updated_at: string;
}

export interface StreamIngestJobProgressOptions {
  readonly jobId: number;
  readonly signal?: AbortSignal;
  readonly onEvent: (event: IngestProgressEvent) => void;
}

type UnknownRecord = Record<string, unknown>;

interface SseFrame {
  readonly event: string;
  readonly data: string;
}

const INGEST_STATUSES: readonly IngestJobSchema["status"][] = [
  "queued",
  "parsing",
  "chunking",
  "embedding",
  "summarizing",
  "ready",
  "failed",
];

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isIngestStatus(value: string): value is IngestJobSchema["status"] {
  return (INGEST_STATUSES as readonly string[]).includes(value);
}

function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" &&
      error instanceof DOMException &&
      error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

/** Read enough of a failed response to keep FastAPI's stable error shape. */
async function readFailure(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    const text = await response.text();
    if (text.length > 0) {
      payload = JSON.parse(text) as unknown;
    }
  } catch {
    payload = null;
  }

  const code = (isRecord(payload) ? stringValue(payload.error) : null) ?? "http_error";
  const sessionFailure =
    response.status === 401 &&
    (code === "authentication_required" || code === "unauthorized");
  if (
    typeof window !== "undefined" &&
    (sessionFailure || code === "account_disabled")
  ) {
    window.dispatchEvent(new Event("apsor-archive:unauthorized"));
  }

  const detail =
    (isRecord(payload) ? stringValue(payload.detail) : null) ??
    (isRecord(payload) ? stringValue(payload.error) : null) ??
    (response.statusText ||
      translate(getActiveLocale(), "core.errors.generic"));
  return new ApiError(response.status, code, detail, payload);
}

function nextDelimiter(
  buffer: string,
): { readonly index: number; readonly length: number } | null {
  const candidates: ReadonlyArray<{ index: number; length: number }> = [
    { index: buffer.indexOf("\n\n"), length: 2 },
    { index: buffer.indexOf("\r\n\r\n"), length: 4 },
    { index: buffer.indexOf("\r\r"), length: 2 },
  ].filter((candidate) => candidate.index >= 0);

  if (candidates.length === 0) {
    return null;
  }
  return candidates.reduce((earliest, candidate) =>
    candidate.index < earliest.index ? candidate : earliest,
  );
}

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of raw.split(/\r\n|\n|\r/)) {
    if (line.length === 0 || line.startsWith(":")) {
      continue;
    }
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join("\n") };
}

/** Normalize one compact progress frame, ignoring unknown or malformed data. */
function toProgressEvent(frame: SseFrame): IngestProgressEvent | null {
  if (!(INGEST_EVENT_TYPES as readonly string[]).includes(frame.event)) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(frame.data) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  const id = numberValue(parsed.id);
  const status = stringValue(parsed.status);
  const progressPct = numberValue(parsed.progress_pct);
  const updatedAt = stringValue(parsed.updated_at);
  if (
    id === null ||
    status === null ||
    !isIngestStatus(status) ||
    progressPct === null ||
    updatedAt === null
  ) {
    return null;
  }
  return {
    id,
    status,
    stage: stringValue(parsed.stage),
    progress_pct: progressPct,
    stage_done: numberValue(parsed.stage_done),
    stage_total: numberValue(parsed.stage_total),
    stage_unit: stringValue(parsed.stage_unit),
    chunks_total: numberValue(parsed.chunks_total),
    chunks_embedded: numberValue(parsed.chunks_embedded),
    file_id: numberValue(parsed.file_id),
    error_code: stringValue(parsed.error_code),
    error_detail: stringValue(parsed.error_detail),
    updated_at: updatedAt,
  };
}

/**
 * Merge one compact event into the caller's enqueue snapshot.
 *
 * Every field the event carries is authoritative, including explicit nulls that
 * clear a completed stage count. Fields the compact event omits (path, MIME
 * type, attempts, timestamps) keep the snapshot value.
 */
export function mergeIngestProgressEvent(
  job: IngestJobSchema,
  event: IngestProgressEvent,
): IngestJobSchema {
  return {
    ...job,
    id: event.id,
    status: event.status,
    stage: event.stage,
    progress_pct: event.progress_pct,
    stage_done: event.stage_done,
    stage_total: event.stage_total,
    stage_unit: event.stage_unit,
    chunks_total: event.chunks_total,
    chunks_embedded: event.chunks_embedded,
    file_id: event.file_id,
    error_code: event.error_code,
    error_detail: event.error_detail,
    updated_at: event.updated_at,
  };
}

/**
 * True when an incoming event is strictly newer than the current job snapshot.
 * Pub/Sub can deliver duplicates or reordered messages after a reconnect.
 */
export function isNewerIngestUpdate(
  currentUpdatedAt: string,
  incomingUpdatedAt: string,
): boolean {
  const current = Date.parse(currentUpdatedAt);
  const incoming = Date.parse(incomingUpdatedAt);
  if (Number.isNaN(current) || Number.isNaN(incoming)) {
    return true;
  }
  return incoming > current;
}

async function readProgressStream(
  response: Response,
  onEvent: (event: IngestProgressEvent) => void,
): Promise<void> {
  if (!response.body) {
    throw new ApiError(
      502,
      "stream_unavailable",
      translate(getActiveLocale(), "library.ingest.streamUnavailable"),
      null,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consume = (raw: string) => {
    const frame = parseFrame(raw);
    if (!frame) {
      return;
    }
    const event = toProgressEvent(frame);
    if (event) {
      onEvent(event);
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let delimiter = nextDelimiter(buffer);
      while (delimiter) {
        consume(buffer.slice(0, delimiter.index));
        buffer = buffer.slice(delimiter.index + delimiter.length);
        delimiter = nextDelimiter(buffer);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim().length > 0) {
      consume(buffer);
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Open one SSE progress stream with cookie authentication.
 *
 * The promise resolves when the server closes the stream. Aborting `signal`
 * rejects the fetch; the durable ingestion job is not cancelled.
 */
export async function streamIngestJobProgress({
  jobId,
  signal,
  onEvent,
}: StreamIngestJobProgressOptions): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/files/ingest-jobs/${jobId}/events`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "text/event-stream" },
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ApiError(
      0,
      "network_error",
      translate(getActiveLocale(), "core.errors.network_error"),
      null,
    );
  }

  if (!response.ok) {
    throw await readFailure(response);
  }
  await readProgressStream(response, onEvent);
}
