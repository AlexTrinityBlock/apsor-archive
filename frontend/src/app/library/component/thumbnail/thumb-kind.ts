import type { PathFileSchema } from "../../../generated-apis-types/schemas";
import { basename } from "../../../../lib/format";

/** The preview a library file card can show for a stored original. */
export type ThumbKind = "image" | "pdf" | "docx" | "pptx" | "file";

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"]);

/**
 * Classify a stored path by the lowercase extension of its real basename.
 *
 * `PathFileSchema` carries no MIME type or extension, so the archived path is
 * the only local signal. The path is inspected as text and never rendered.
 */
export function thumbKindFor(rawPath: string): ThumbKind {
  const name = basename(rawPath).toLowerCase();
  const dot = name.lastIndexOf(".");
  const extension = dot >= 0 ? name.slice(dot) : "";
  if (IMAGE_EXTENSIONS.has(extension)) {
    return "image";
  }
  if (extension === ".pdf") {
    return "pdf";
  }
  if (extension === ".docx") {
    return "docx";
  }
  if (extension === ".pptx") {
    return "pptx";
  }
  return "file";
}

/**
 * Cache key for one stored version. A re-ingested file keeps its id but gets a
 * new update time, so the replacement cannot reuse the previous image.
 */
export function thumbCacheKey(
  file: Pick<PathFileSchema, "file_id" | "update_time">,
): string {
  return `${file.file_id}:${file.update_time}`;
}
