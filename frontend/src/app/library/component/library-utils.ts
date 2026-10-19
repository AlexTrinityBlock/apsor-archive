import { ApiError } from "../../../apis/fetch-client";
import { basename, humanFileKind } from "../../../lib/format";
import {
  getFile,
  getIngestJob,
} from "../../generated-apis-types/files/files";
import type {
  FileSchema,
  IngestJobSchema,
} from "../../generated-apis-types/schemas";

/** Upload ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Text creation ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;

/** The two presentations of the same shelf. */
export type LibraryView = "board" | "list";

/** The durable ingestion stages reported by `IngestJobSchema.status`. */
export type IngestStage =
  | "queued"
  | "parsing"
  | "chunking"
  | "embedding"
  | "summarizing"
  | "ready"
  | "failed";

/** Short editorial labels for the durable job stages. */
export const INGEST_STAGE_LABELS: Record<IngestStage, string> = {
  queued: "Queued",
  parsing: "Parsing",
  chunking: "Chunking",
  embedding: "Embedding",
  summarizing: "Summarizing",
  ready: "Ready",
  failed: "Failed",
};

/** Resolves a stage label, with a useful fallback for pre-job work. */
export function ingestStageLabel(
  stage: IngestStage | null | undefined,
  fallback = "Preparing",
): string {
  return stage ? INGEST_STAGE_LABELS[stage] : fallback;
}

/** The lifecycle of one file in the drag-and-drop intake tray. */
export type LibraryUploadStatus = "queued" | "uploading" | "processing" | "done" | "error";

/** One file in the drag-and-drop intake tray. */
export interface LibraryUploadTask {
  readonly id: number;
  readonly name: string;
  readonly targetPath: string;
  readonly status: LibraryUploadStatus;
  readonly message?: string;
  readonly rejected?: boolean;
  readonly jobId?: number;
  readonly stage?: IngestStage;
  readonly progressPct?: number;
  readonly chunksTotal?: number | null;
  readonly chunksEmbedded?: number | null;
  readonly fileId?: number | null;
}

/** Copies the durable job's progress fields onto a tray task. */
export function taskProgressFromJob(
  job: IngestJobSchema,
): Pick<
  LibraryUploadTask,
  "jobId" | "stage" | "progressPct" | "chunksTotal" | "chunksEmbedded" | "fileId"
> {
  return {
    jobId: job.id,
    stage: job.status,
    progressPct: job.progress_pct,
    chunksTotal: job.chunks_total,
    chunksEmbedded: job.chunks_embedded,
    fileId: job.file_id,
  };
}

/** How often the UI asks the durable job endpoint for progress. */
export const INGEST_POLL_INTERVAL_MS = 1000;

/** The UI stops waiting after half an hour; the job itself keeps running. */
export const INGEST_POLL_TIMEOUT_MS = 30 * 60 * 1000;

/** Readable failure text for a job: `error_detail`, then `error_code`. */
export function ingestJobFailureMessage(job: IngestJobSchema): string {
  return (
    job.error_detail?.trim() ||
    job.error_code ||
    "The archive could not finish ingesting this file."
  );
}

/** A failed ingest job, carrying the readable detail shown in the UI. */
export class IngestJobFailureError extends Error {
  readonly code: string;

  readonly job: IngestJobSchema;

  constructor(job: IngestJobSchema) {
    super(ingestJobFailureMessage(job));
    this.name = "IngestJobFailureError";
    this.code = job.error_code ?? "ingest_failed";
    this.job = job;
  }
}

/** The job outlived the UI polling window; it may still finish server-side. */
export class IngestPollTimeoutError extends Error {
  readonly job: IngestJobSchema;

  constructor(job: IngestJobSchema) {
    super("This file is still processing. You can close the dialog and check the library later.");
    this.name = "IngestPollTimeoutError";
    this.job = job;
  }
}

/** Recognises the abort surfaced by `fetch` and the polling delay. */
export function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" &&
      error instanceof DOMException &&
      error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

function abortError(): DOMException {
  return new DOMException("Ingest polling was cancelled.", "AbortError");
}

function waitForPoll(intervalMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(abortError());
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve();
    }, intervalMs);
    function handleAbort() {
      window.clearTimeout(timer);
      reject(abortError());
    }
    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}

export interface WaitForIngestJobOptions {
  readonly signal?: AbortSignal;
  readonly intervalMs?: number;
  readonly timeoutMs?: number;
  readonly onUpdate?: (job: IngestJobSchema) => void;
}

async function readIngestJob(jobId: number, signal?: AbortSignal): Promise<IngestJobSchema> {
  return getIngestJob(jobId, { signal });
}

/**
 * Polls one durable ingestion job until it is ready, fails, or exceeds the
 * wait budget. Every iteration awaits both the request and the delay, so there
 * are never overlapping timers.
 *
 * @param jobId - Durable job returned by the async upload endpoints.
 * @param options - Cancellation signal, cadence, deadline, and progress sink.
 * @returns The terminal job, whose `file_id` points at the published file.
 * @throws {IngestJobFailureError} When the job reports `failed`.
 * @throws {IngestPollTimeoutError} When the UI wait budget expires.
 */
export async function waitForIngestJob(
  jobId: number,
  options: WaitForIngestJobOptions = {},
): Promise<IngestJobSchema> {
  const deadline = Date.now() + (options.timeoutMs ?? INGEST_POLL_TIMEOUT_MS);
  const intervalMs = options.intervalMs ?? INGEST_POLL_INTERVAL_MS;
  let job = await readIngestJob(jobId, options.signal);

  for (;;) {
    options.onUpdate?.(job);
    if (job.status === "ready") {
      return job;
    }
    if (job.status === "failed") {
      throw new IngestJobFailureError(job);
    }
    if (Date.now() >= deadline) {
      throw new IngestPollTimeoutError(job);
    }
    await waitForPoll(intervalMs, options.signal);
    job = await readIngestJob(jobId, options.signal);
  }
}

/**
 * Waits for a job and then loads the published file. The extra request is only
 * made once the backend has marked the job ready.
 *
 * @param jobId - Durable job returned by the async upload endpoints.
 * @param options - The same options accepted by `waitForIngestJob`.
 * @returns The fully indexed file.
 */
export async function waitForIngestedFile(
  jobId: number,
  options: WaitForIngestJobOptions = {},
): Promise<FileSchema> {
  const job = await waitForIngestJob(jobId, options);
  if (job.file_id === null) {
    throw new Error("The ingest job finished without a file.");
  }
  return getFile(job.file_id, { signal: options.signal });
}

export const ACCEPTED_FILE_TYPES =
  ".md,.markdown,.txt,.csv,.json,.log,.pdf,.docx,.jpg,.jpeg,.png,.webp";

const ALLOWED_EXTENSIONS = [
  ".md",
  ".markdown",
  ".txt",
  ".csv",
  ".json",
  ".log",
  ".pdf",
  ".docx",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
] as const;

/** Reads a positive integer from a query parameter without accepting prefixes. */
export function parsePositiveInt(raw: string | null): number | null {
  if (!raw || !/^\d+$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Keeps a browsed path absolute so breadcrumbs and API calls always agree. */
export function normalizeLibraryPath(raw: string | null): string {
  if (!raw) {
    return "/";
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return "/";
  }
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

/** Normalizes a full archive path typed into the intake dialog. */
export function normalizeArchivePath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const prefixed = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  const collapsed = prefixed.replace(/\/{2,}/g, "/");
  if (collapsed.length > 1 && collapsed.endsWith("/")) {
    return collapsed.slice(0, -1);
  }
  return collapsed;
}

/** Omits the default root path so a clean `/library` URL means the archive root. */
export function pathParamValue(path: string): string | null {
  return path === "/" ? null : path;
}

/** Returns true when a path has a final segment, i.e. a file name. */
export function hasFileName(path: string): boolean {
  const segments = path.split("/").filter(Boolean);
  return segments.length > 0;
}

/** Returns true when the browser-selected file carries a supported suffix. */
export function isAcceptedFileName(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/** Rejects a browser file name that could escape the chosen folder. */
export function isSafeUploadName(name: string): boolean {
  const trimmed = name.trim();
  return (
    trimmed.length > 0 &&
    trimmed === name &&
    !trimmed.includes("/") &&
    !trimmed.includes("\\") &&
    trimmed !== "." &&
    trimmed !== ".."
  );
}

/** Joins a folder path and a file name into one absolute archive path. */
export function joinArchivePath(folderPath: string, fileName: string): string {
  const folder = normalizeArchivePath(folderPath);
  const name = fileName.replace(/^\/+/, "");
  if (!name) {
    return folder;
  }
  return folder === "/" ? `/${name}` : `${folder}/${name}`;
}

/** Compares two archive paths after tolerant normalization. */
export function sameArchivePath(left: string, right: string): boolean {
  return normalizeArchivePath(left) === normalizeArchivePath(right);
}

/** The allowed-type hint shared by the intake dialog and drag-and-drop tray. */
export const ACCEPTED_FILE_HINT =
  ".md, .markdown, .txt, .csv, .json, .log, .pdf, .docx, .jpg, .jpeg, .png, .webp";

/** The compact kind label shown in the file table. */
export function fileKindLabel(rawPath: string): string {
  const kind = humanFileKind(rawPath);
  return kind.length > 0 ? kind.toUpperCase() : "FILE";
}

/** Names the place the reader's back button returns to. */
export function readerBackLabel(path: string, hasQuery: boolean): string {
  if (hasQuery) {
    return "Back to path matches";
  }
  if (path === "/") {
    return "Back to archive root";
  }
  return `Back to ${basename(path)}`;
}

/** Clamps a requested chunk to the file's 1-based range. */
export function clampChunk(chunk: number, totalChunks: number): number {
  const lastChunk = Math.max(1, totalChunks);
  return Math.min(Math.max(1, chunk), lastChunk);
}

/** Measures UTF-8 bytes for the 2 MB text ceiling. */
export function textByteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

/** Extracts a calm, human message from an API or network failure. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail || error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string" && error.trim().length > 0) {
    return error;
  }
  return "The archive could not complete that request.";
}

/** Detects a 404 so the page can show a calm not-found panel instead. */
export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
