/**
 * Viewer-only formatting, classification, and fetch helpers.
 *
 * Binary and stream responses deliberately bypass `apiFetch`: that mutator
 * parses JSON/text and is not suitable for PDFs, DOCX packages, or images.
 * Every URL here is derived from a database id or a generated API helper.
 */
import { ApiError } from "../../../apis/fetch-client";
import {
  getDownloadFileUrl,
  getGetFileContentUrl,
} from "../../generated-apis-types/files/files";
import type { FileSchema } from "../../generated-apis-types/schemas";

export type ViewerKind =
  | "pdf"
  | "docx"
  | "image"
  | "markdown"
  | "json"
  | "csv"
  | "text"
  | "unsupported";

/** A binary/text response failure with FastAPI's stable error code when present. */
export class ViewerResourceError extends Error {
  readonly status: number;

  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ViewerResourceError";
    this.status = status;
    this.code = code;
  }
}

interface ErrorRecord {
  readonly [key: string]: unknown;
}

function isRecord(value: unknown): value is ErrorRecord {
  return typeof value === "object" && value !== null;
}

async function responseError(response: Response): Promise<ViewerResourceError> {
  let code = "http_error";
  let detail = response.statusText || `Request failed with status ${response.status}`;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const payload: unknown = await response.json();
      if (isRecord(payload)) {
        if (typeof payload.error === "string" && payload.error.length > 0) {
          code = payload.error;
        }
        if (typeof payload.detail === "string" && payload.detail.length > 0) {
          detail = payload.detail;
        }
      }
    } catch {
      // Keep the HTTP status text when the error body is not valid JSON.
    }
  }
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("dendromatrix:unauthorized"));
  }
  return new ViewerResourceError(response.status, code, detail);
}

/** Same-origin inline URL for a stored file original. */
export function fileContentUrl(fileId: number): string {
  return getGetFileContentUrl(fileId);
}

/** Same-origin attachment URL for a stored file original. */
export function fileDownloadUrl(fileId: number): string {
  return getDownloadFileUrl(fileId);
}

/** Fetch a text-like file without JSON coercion. */
export async function fetchViewerText(url: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      Accept: "text/plain, text/markdown, text/csv, application/json, */*",
    },
    signal,
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.text();
}

/** Fetch an original binary for DOCX or PDF rendering. */
export async function fetchViewerBinary(
  url: string,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/octet-stream, */*" },
    signal,
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.arrayBuffer();
}

/** Classify a file by its stored MIME type first and its extension second. */
export function classifyFile(
  file: Pick<FileSchema, "mime_type" | "extension">,
): ViewerKind {
  const mime = file.mime_type.split(";", 1)[0].trim().toLowerCase();
  const extension = file.extension.trim().toLowerCase();

  if (mime === "application/pdf" || extension === ".pdf") {
    return "pdf";
  }
  if (mime.includes("wordprocessingml.document") || extension === ".docx") {
    return "docx";
  }
  if (
    mime.startsWith("image/") ||
    [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"].includes(extension)
  ) {
    return "image";
  }
  if (extension === ".json" || mime === "application/json" || mime.endsWith("+json")) {
    return "json";
  }
  if (extension === ".csv" || mime.includes("csv")) {
    return "csv";
  }
  if (extension === ".md" || extension === ".markdown" || mime === "text/markdown") {
    return "markdown";
  }
  if (mime.startsWith("text/") || extension === ".txt" || extension === ".log") {
    return "text";
  }
  return "unsupported";
}

/** Human label for a viewer kind. */
export function kindLabel(kind: ViewerKind): string {
  switch (kind) {
    case "pdf":
      return "PDF document";
    case "docx":
      return "Word document";
    case "image":
      return "Image";
    case "markdown":
      return "Markdown";
    case "json":
      return "JSON";
    case "csv":
      return "CSV sheet";
    case "text":
      return "Text";
    default:
      return "Original file";
  }
}

/** Which text sheet mode a file needs. */
export function textMode(kind: ViewerKind): "markdown" | "json" | "csv" | "text" {
  if (kind === "markdown" || kind === "json" || kind === "csv") {
    return kind;
  }
  return "text";
}

/** Parse a route id without accepting zero, negatives, or suffixes. */
export function parseViewerId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/** Read an HTTP status from either the generated client or viewer fetch errors. */
export function viewerErrorStatus(error: unknown): number | null {
  if (error instanceof ApiError || error instanceof ViewerResourceError) {
    return error.status;
  }
  return null;
}

/** A short, safe error message for viewer states. */
export function viewerErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail || error.message;
  }
  if (error instanceof ViewerResourceError) {
    return error.message;
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The archive could not open this resource.";
}

/** Pretty-print JSON without ever executing or transforming its values. */
export function prettyJson(content: string): { formatted: string; valid: boolean } {
  try {
    const parsed: unknown = JSON.parse(content);
    return { formatted: JSON.stringify(parsed, null, 2), valid: true };
  } catch {
    return { formatted: content, valid: false };
  }
}

function overlapLength(previous: string, next: string): number {
  const limit = Math.min(previous.length, next.length);
  if (limit === 0) {
    return 0;
  }
  const prefix = new Array<number>(next.length).fill(0);
  for (let index = 1; index < next.length; index += 1) {
    let matched = prefix[index - 1];
    while (matched > 0 && next[index] !== next[matched]) {
      matched = prefix[matched - 1];
    }
    if (next[index] === next[matched]) {
      matched += 1;
    }
    prefix[index] = matched;
  }

  let matched = 0;
  for (let index = previous.length - limit; index < previous.length; index += 1) {
    while (matched > 0 && previous[index] !== next[matched]) {
      matched = prefix[matched - 1];
    }
    if (previous[index] === next[matched]) {
      matched += 1;
    }
    if (matched === next.length) {
      if (index === previous.length - 1) {
        return next.length;
      }
      matched = prefix[matched - 1];
    }
  }
  return matched;
}

/** Count lines without allocating one string per line. */
export function countLines(content: string): number {
  if (content.length === 0) {
    return 0;
  }
  let lines = 1;
  for (let index = 0; index < content.length; index += 1) {
    if (content.charCodeAt(index) === 10) {
      lines += 1;
    }
  }
  return lines;
}

/** Merge overlapping indexed chunks back into one readable sequence. */
export function joinChunkContents(
  chunks: readonly { readonly chunk: number; readonly content: string }[],
): string {
  const ordered = [...chunks].sort((left, right) => left.chunk - right.chunk);
  if (ordered.length === 0) {
    return "";
  }
  let merged = ordered[0].content;
  for (let index = 1; index < ordered.length; index += 1) {
    const next = ordered[index].content;
    const overlap = overlapLength(merged, next);
    merged = `${merged}${overlap > 0 ? "\n" : "\n\n"}${next.slice(overlap)}`;
  }
  return merged;
}

interface CsvTable {
  readonly headers: readonly string[];
  readonly rows: readonly (readonly string[])[];
  readonly totalRows: number;
  readonly truncated: boolean;
}

const CSV_MAX_ROWS = 500;
const CSV_MAX_COLUMNS = 40;

function detectDelimiter(text: string): string {
  const sample = text.slice(0, 4_000);
  const candidates = [",", ";", "\t"];
  let best = ",";
  let bestCount = -1;
  for (const candidate of candidates) {
    const count = sample.split(candidate).length - 1;
    if (count > bestCount) {
      best = candidate;
      bestCount = count;
    }
  }
  return best;
}

function parseCsvRows(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
    } else if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === delimiter) {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (character === "\r") {
      if (text[index + 1] === "\n") {
        index += 1;
      }
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => cell.trim().length > 0));
}

/** Parse a CSV document into a bounded, read-only table. */
export function parseCsv(content: string): CsvTable {
  const text = content.replace(/^\uFEFF/, "");
  const delimiter = detectDelimiter(text);
  const raw = parseCsvRows(text, delimiter);
  const headers = (raw[0] ?? []).slice(0, CSV_MAX_COLUMNS);
  const body = raw.slice(1).map((row) => row.slice(0, CSV_MAX_COLUMNS));
  return {
    headers,
    rows: body.slice(0, CSV_MAX_ROWS),
    totalRows: body.length,
    truncated: body.length > CSV_MAX_ROWS,
  };
}
