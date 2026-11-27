import type { PathFileSchema } from "../../../generated-apis-types/schemas";
import {
  readThumbnail,
  type ThumbnailInfo,
} from "../../../viewer/component/thumbnail";
import type { ThumbKind } from "./thumb-kind";

/**
 * The server WebP thumbnail a library card should paint, or `null` when the
 * card must fall back to the client-side renderer (older files not yet
 * backfilled, Office files without an embedded preview, or a failed load).
 */
export function serverThumbnailFor(
  file: Pick<PathFileSchema, "has_original" | "thumbnail">,
  failed: boolean,
): ThumbnailInfo | null {
  if (failed || !file.has_original) {
    return null;
  }
  return readThumbnail(file.thumbnail);
}

/** The existing image class that fits each kind's card framing. */
export function serverThumbnailClass(kind: ThumbKind): string {
  switch (kind) {
    case "image":
      return "library-thumb__image";
    case "xlsx":
      return "library-thumb__sheet";
    default:
      return "library-thumb__document";
  }
}
