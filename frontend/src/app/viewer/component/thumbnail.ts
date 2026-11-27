import { getGetFileThumbnailUrl } from "../../generated-apis-types/files/files";

/**
 * A server-rendered WebP thumbnail: its cache-busting version and pixel size.
 * The size is known before the image loads, so a card can reserve the exact
 * box and never shift when the bytes arrive.
 */
export interface ThumbnailInfo {
  readonly version: string;
  readonly width: number;
  readonly height: number;
}

const VERSION_PATTERN = /^[0-9a-f]{1,64}$/;
const MAX_EDGE = 512;

function dimension(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return null;
  }
  return value >= 1 && value <= MAX_EDGE ? value : null;
}

/** Parse untrusted tool or API data into a thumbnail, or `null`. */
export function readThumbnail(value: unknown): ThumbnailInfo | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const version = record.version;
  const width = dimension(record.width);
  const height = dimension(record.height);
  if (typeof version !== "string" || !VERSION_PATTERN.test(version)) {
    return null;
  }
  if (width === null || height === null) {
    return null;
  }
  return { version, width, height };
}

/** Versioned URL; the server marks a matching version immutable. */
export function fileThumbnailUrl(fileId: number, version: string): string {
  return getGetFileThumbnailUrl(fileId, { v: version });
}

/** CSS `aspect-ratio` value for a thumbnail box. */
export function thumbnailAspect(thumbnail: ThumbnailInfo): string {
  return `${thumbnail.width} / ${thumbnail.height}`;
}

/** Height divided by width, used to seed page placeholders before measuring. */
export function thumbnailPageRatio(thumbnail: ThumbnailInfo): number {
  return thumbnail.height / thumbnail.width;
}
