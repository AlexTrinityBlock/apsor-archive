import { ApiError } from "../../../apis/fetch-client";
import { truncate } from "../../../lib/format";
import type { MediaSchema } from "../../generated-apis-types/schemas";

/** The image types the media API accepts. */
export const MEDIA_ACCEPT = "image/jpeg,image/png,image/webp";

/** The API's upload ceiling, mirrored for a faster client-side hint. */
export const MAX_MEDIA_BYTES = 10 * 1024 * 1024;

const ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"] as const;

/** Returns true when a browser-selected file looks like an accepted image. */
export function isSupportedMediaFile(file: File): boolean {
  const mime = file.type.trim().toLowerCase();
  if (mime.length > 0 && ALLOWED_MIME_TYPES.has(mime)) {
    return true;
  }
  const name = file.name.trim().toLowerCase();
  return ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension));
}

/** Adds the leading slash the media API requires, or returns null when blank. */
export function normalizeMediaUploadPath(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const prefixed = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return prefixed.replace(/\/{2,}/g, "/");
}

/** Mirrors the media API's path rules before a request is sent. */
export function validateMediaUploadPath(path: string | null): string | null {
  if (path === null) {
    return null;
  }
  if (path.length > 512) {
    return "Keep the media path under 512 characters.";
  }
  if (path.endsWith("/")) {
    return "Enter the full path, including the file name.";
  }
  if (path.includes("\\")) {
    return "Use forward slashes in the media path.";
  }
  if (path.split("/").some((segment) => segment === "..")) {
    return "Path traversal segments are not allowed.";
  }
  return null;
}

/** Normalizes comma-separated tags into the string the upload form expects. */
export function normalizeMediaTags(value: string): string | null {
  const tags = value
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
  const unique = Array.from(new Set(tags));
  return unique.length > 0 ? unique.join(", ") : null;
}

/** The visible card and dialog title, falling back through caption and filename. */
export function mediaDisplayTitle(
  media: Pick<MediaSchema, "title" | "caption" | "file_name">,
): string {
  const title = media.title.replace(/\s+/g, " ").trim();
  if (title.length > 0) {
    return title;
  }
  const caption = media.caption.replace(/\s+/g, " ").trim();
  if (caption.length > 0) {
    return truncate(caption, 72);
  }
  return media.file_name;
}

/** Alt text prefers the generated title, then the caption, then the filename. */
export function mediaAltText(
  media: Pick<MediaSchema, "title" | "caption" | "file_name">,
): string {
  const title = media.title.replace(/\s+/g, " ").trim();
  if (title.length > 0) {
    return title;
  }
  const caption = media.caption.replace(/\s+/g, " ").trim();
  if (caption.length > 0) {
    return truncate(caption, 180);
  }
  return media.file_name;
}

/** A readable document-type label without inventing a taxonomy. */
export function mediaDocumentType(media: Pick<MediaSchema, "document_type">): string {
  const value = media.document_type.replace(/[_-]+/g, " ").trim();
  return value.length > 0 ? value : "unclassified";
}

/** The compact, archival dimensions label. */
export function mediaDimensions(media: Pick<MediaSchema, "width" | "height">): string {
  if (media.width > 0 && media.height > 0) {
    return `${media.width} × ${media.height}`;
  }
  return "—";
}

/** A card excerpt from the caption, or the summary when no caption exists. */
export function mediaCaptionExcerpt(
  media: Pick<MediaSchema, "caption" | "summary">,
  maxLength = 150,
): string {
  const text = media.caption.trim().length > 0 ? media.caption : media.summary;
  return truncate(text, maxLength);
}

/** Fixed-precision display for a hybrid search score. */
export function formatMediaScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(3) : "—";
}

/** Detects the API's "no vision provider" response in one place. */
export function isProviderUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 503 || error.code === "media_not_configured")
  );
}

/** Detects upstream caption failures so the UI can explain the 502 detail. */
export function isCaptionFailure(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 502 || error.code === "media_caption_failed")
  );
}

/** Extracts the API's stable error detail, with a calm fallback. */
export function mediaErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail || error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string" && error.trim().length > 0) {
    return error;
  }
  return "The media archive could not complete that request.";
}
