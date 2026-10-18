import { ApiError } from "../../../apis/fetch-client";
import { basename, humanFileKind } from "../../../lib/format";

/** Upload ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Text creation ceiling enforced by the API, mirrored here for a faster hint. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;

/** The two presentations of the same shelf. */
export type LibraryView = "board" | "list";

/** One file in the drag-and-drop intake tray. */
export interface LibraryUploadTask {
  readonly id: number;
  readonly name: string;
  readonly targetPath: string;
  readonly status: "queued" | "uploading" | "done" | "error";
  readonly message?: string;
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
