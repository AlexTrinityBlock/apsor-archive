import type { CSSProperties } from "react";

import {
  thumbnailAspect,
  type ThumbnailInfo,
} from "../../viewer/component/thumbnail";

/** A presented-resource preview never exceeds this edge, in CSS pixels. */
export const PREVIEW_MAX_EDGE = 420;

/** Width of a preview box that fits a thumbnail inside the 420px square. */
export function previewBoxWidth(thumbnail: ThumbnailInfo): number {
  const ratio = thumbnail.width / thumbnail.height;
  return Math.round(ratio >= 1 ? PREVIEW_MAX_EDGE : PREVIEW_MAX_EDGE * ratio);
}

/**
 * Inline size for a framed preview. The aspect ratio comes from the server
 * thumbnail, so the box is final before any image or PDF byte arrives.
 */
export function framedThumbnailStyle(thumbnail: ThumbnailInfo): CSSProperties {
  return {
    width: `min(100%, ${previewBoxWidth(thumbnail)}px)`,
    aspectRatio: thumbnailAspect(thumbnail),
  };
}
