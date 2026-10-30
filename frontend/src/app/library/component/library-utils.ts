import type { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../../../apis/fetch-client";
import { basename } from "../../../lib/format";
import {
  getActiveLocale,
  translate,
  translateApiErrorWithActiveLocale,
  type TranslationKey,
} from "../../i18n";
import {
  getFile,
  getIngestJob,
} from "../../generated-apis-types/files/files";
import type {
  DirectorySchema,
  FileSchema,
  IngestJobSchema,
  PathFileSchema,
  PathListingSchema,
} from "../../generated-apis-types/schemas";

/** Upload ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Text creation ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;

/** The two workspaces that share one path listing. */
export type LibraryTab = "files" | "media";

/** The two file operation modes used by move/copy dialogs and drag drops. */
export type FileOperationMode = "move" | "copy";

/** The two presentations of the same file shelf. */
export type LibraryView = "board" | "list";

/** Client-side ordering for the path listing (the API exposes no sort param). */
export type LibrarySort = "modified" | "name" | "size" | "type";

export const LIBRARY_SORT_OPTIONS: readonly LibrarySort[] = [
  "modified",
  "name",
  "size",
  "type",
];

/** The image extensions the merged media gallery recognises. */
export const IMAGE_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".gif",
  ".avif",
] as const;

/** The image types the file ingest endpoint currently accepts. */
export const IMAGE_UPLOAD_ACCEPT = ".jpg,.jpeg,.png,.webp";

/** One file operation target; both `FileSchema` and `PathFileSchema` map to it. */
export interface FileOperationTarget {
  readonly file_id: number;
  readonly file_name: string;
  readonly raw_file_path: string;
}

/** The durable ingestion stages reported by `IngestJobSchema.status`. */
export type IngestStage =
  | "queued"
  | "parsing"
  | "chunking"
  | "embedding"
  | "summarizing"
  | "ready"
  | "failed";

/** Translation keys for the durable job stages, resolved by the components. */
export const INGEST_STAGE_KEYS = {
  queued: "library.ingest.stage.queued",
  parsing: "library.ingest.stage.parsing",
  chunking: "library.ingest.stage.chunking",
  embedding: "library.ingest.stage.embedding",
  summarizing: "library.ingest.stage.summarizing",
  ready: "library.ingest.stage.ready",
  failed: "library.ingest.stage.failed",
} as const satisfies Record<IngestStage, TranslationKey>;

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
  /** Kept only while the tray is open so a failed upload can be retried. */
  readonly sourceFile?: File;
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
    translate(getActiveLocale(), "library.ingest.failureFallback")
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
    super(translate(getActiveLocale(), "library.ingest.pollTimeout"));
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
    throw new Error(translate(getActiveLocale(), "library.ingest.missingFile"));
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

/** Returns true when a stored file name is one of the gallery image types. */
export function isImageFileName(name: string): boolean {
  const lower = name.toLowerCase();
  return IMAGE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/** Whether a stored path is a Markdown document the editor can open. */
export function isMarkdownFile(rawPath: string): boolean {
  const lower = rawPath.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".markdown");
}

/**
 * The triggering event for a context menu. A mouse event already satisfies this
 * interface; keyboard use goes through `contextMenuTriggerFromKeyboard`, which
 * builds an equivalent object from the button's position.
 */
export interface LibraryContextMenuTrigger {
  readonly clientX: number;
  readonly clientY: number;
  readonly currentTarget: EventTarget | null;
  readonly preventDefault: () => void;
  readonly stopPropagation: () => void;
}

/** The ContextMenu key and Shift+F10 open the same menu as a right click. */
export function isContextMenuKey(event: {
  readonly key: string;
  readonly shiftKey: boolean;
}): boolean {
  return event.key === "ContextMenu" || (event.shiftKey && event.key === "F10");
}

/** Build the menu coordinates from the center of the trigger button's visible area. */
export function contextMenuTriggerFromKeyboard(
  target: HTMLElement,
): LibraryContextMenuTrigger {
  const rect = target.getBoundingClientRect();
  return {
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
    currentTarget: target,
    preventDefault: () => undefined,
    stopPropagation: () => undefined,
  };
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

/** Validates one folder leaf name for rename, move, and copy requests. */
export function isSafeFolderName(name: string): boolean {
  if (!isSafeUploadName(name) || name.length > 255) {
    return false;
  }
  for (const character of name) {
    const code = character.charCodeAt(0);
    if (code < 0x20 || code === 0x7f) {
      return false;
    }
  }
  return true;
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

/** True when `path` is `ancestor` itself or lives anywhere below it. */
export function isPathInside(path: string, ancestor: string): boolean {
  const trimmedAncestor = ancestor.replace(/\/$/, "");
  return path === ancestor || path.startsWith(`${trimmedAncestor}/`);
}

/** Rewrites a path below `source` to the matching path below `target`. */
export function remapArchivePath(
  path: string,
  source: string,
  target: string,
): string {
  if (path === source) {
    return target;
  }
  const trimmedSource = source.replace(/\/$/, "");
  if (!path.startsWith(`${trimmedSource}/`)) {
    return path;
  }
  return `${target}${path.slice(source.length)}`;
}

/** The allowed-type hint shared by the intake dialog and the drag-and-drop tray. */
export const ACCEPTED_FILE_HINT =
  ".md, .markdown, .txt, .csv, .json, .log, .pdf, .docx, .jpg, .jpeg, .png, .webp";

/** The compact type pill shown on file cards. */
export function fileKindLabel(rawPath: string): string {
  const name = basename(rawPath);
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toUpperCase() : "FILE";
}

/** Maps a stored file to the minimal target used by move/copy dialogs. */
export function operationTargetFromSchema(file: FileSchema): FileOperationTarget {
  return {
    file_id: file.id,
    file_name: file.file_name,
    raw_file_path: file.raw_file_path,
  };
}

/** Maps a path listing file to the minimal target used by move/copy dialogs. */
export function operationTargetFromPathFile(file: PathFileSchema): FileOperationTarget {
  return {
    file_id: file.file_id,
    file_name: file.file_name,
    raw_file_path: file.raw_file_path,
  };
}

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

function sortFolders(folders: readonly DirectorySchema[]): DirectorySchema[] {
  // Path listings do not expose folder size or timestamps; name stays honest.
  return [...folders].sort((left, right) => COLLATOR.compare(left.name, right.name));
}

function sortFiles(
  files: readonly PathFileSchema[],
  sort: LibrarySort,
): PathFileSchema[] {
  const result = [...files];
  if (sort === "name") {
    return result.sort((left, right) => COLLATOR.compare(left.file_name, right.file_name));
  }
  if (sort === "size") {
    return result.sort((left, right) => right.size_bytes - left.size_bytes);
  }
  if (sort === "type") {
    return result.sort((left, right) => {
      const typeOrder = COLLATOR.compare(
        fileKindLabel(left.raw_file_path),
        fileKindLabel(right.raw_file_path),
      );
      return typeOrder !== 0
        ? typeOrder
        : COLLATOR.compare(left.file_name, right.file_name);
    });
  }
  return result.sort((left, right) => {
    const leftTime = new Date(left.update_time).getTime();
    const rightTime = new Date(right.update_time).getTime();
    const leftValue = Number.isNaN(leftTime) ? 0 : leftTime;
    const rightValue = Number.isNaN(rightTime) ? 0 : rightTime;
    return rightValue - leftValue;
  });
}

/** Orders one listing in the browser; the API has no sort parameter. */
export function sortListing(
  listing: PathListingSchema,
  sort: LibrarySort,
): PathListingSchema {
  return {
    ...listing,
    directories: sortFolders(listing.directories),
    files: sortFiles(listing.files, sort),
  };
}

/** Keeps only files whose stored name is an image extension. */
export function imageFiles(files: readonly PathFileSchema[]): PathFileSchema[] {
  return files.filter((file) => isImageFileName(file.file_name));
}

/** Applies the Media tab's local text filter to image files. */
export function filterImageFiles(
  files: readonly PathFileSchema[],
  query: string,
): PathFileSchema[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return [...files];
  }
  return files.filter(
    (file) =>
      file.file_name.toLowerCase().includes(needle) ||
      file.raw_file_path.toLowerCase().includes(needle),
  );
}

/** True when a paste event landed in a field that owns the clipboard. */
export function isEditablePasteTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

const CLIPBOARD_EXTENSIONS: Record<string, string> = {
  "image/avif": ".avif",
  "image/gif": ".gif",
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
  "application/json": ".json",
  "application/pdf": ".pdf",
  "text/csv": ".csv",
  "text/markdown": ".md",
  "text/plain": ".txt",
};

function clipboardStamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    "-",
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join("");
}

/** Collects file items from a clipboard payload, including unnamed images. */
export function clipboardFiles(data: DataTransfer | null): File[] {
  if (!data) {
    return [];
  }
  const fromFiles = Array.from(data.files ?? []);
  if (fromFiles.length > 0) {
    return fromFiles;
  }
  const files: File[] = [];
  for (const item of Array.from(data.items ?? [])) {
    if (item.kind !== "file") {
      continue;
    }
    const file = item.getAsFile();
    if (file) {
      files.push(file);
    }
  }
  return files;
}

/**
 * Gives a nameless clipboard file a safe archive name. Named files are left
 * untouched so the uploaded path stays predictable.
 */
export function nameClipboardFile(file: File, index: number): File {
  const trimmed = file.name.trim();
  if (trimmed.length > 0) {
    return file;
  }
  const mime = file.type.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  const extension = CLIPBOARD_EXTENSIONS[mime] ?? ".bin";
  const name = `pasted-${clipboardStamp()}-${index + 1}${extension}`;
  return new File([file], name, {
    type: file.type,
    lastModified: file.lastModified,
  });
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

export interface LibraryInvalidateOptions {
  readonly paths?: boolean;
  readonly stats?: boolean;
  readonly timeline?: boolean;
  readonly search?: boolean;
  readonly fileIds?: readonly number[];
}

/**
 * Invalidates only the keys a file mutation can change. Path listings, stats,
 * and timeline use path-prefix keys; generated file keys are flat strings, so
 * the affected file and its chunk windows are matched by a scoped predicate.
 */
export function invalidateLibraryQueries(
  queryClient: QueryClient,
  options: LibraryInvalidateOptions,
): void {
  if (options.paths) {
    void queryClient.invalidateQueries({ queryKey: ["/api/v1/paths"] });
  }
  if (options.stats) {
    void queryClient.invalidateQueries({ queryKey: ["/api/v1/stats"] });
  }
  if (options.timeline) {
    void queryClient.invalidateQueries({ queryKey: ["/api/v1/timeline"] });
  }
  if (options.search) {
    void queryClient.invalidateQueries({ queryKey: ["/api/v1/search"] });
  }
  for (const fileId of options.fileIds ?? []) {
    const fileKey = `/api/v1/files/${fileId}`;
    void queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey[0];
        return (
          typeof key === "string" &&
          (key === fileKey || key.startsWith(`${fileKey}/chunks/`))
        );
      },
    });
  }
}

/** Extracts a calm, human message from an API or network failure. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return translateApiErrorWithActiveLocale(error, "library.errors.generic");
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  if (typeof error === "string" && error.trim().length > 0) {
    return error;
  }
  return translate(getActiveLocale(), "library.errors.generic");
}

/** Detects a 404 so the page can show a calm not-found panel instead. */
export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
