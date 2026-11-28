import { useState, type CSSProperties, type ReactNode } from "react";

import { fileThumbnailUrl, thumbnailAspect, type ThumbnailInfo } from "./thumbnail";

interface FileThumbnailProps {
  readonly fileId: number;
  readonly thumbnail: ThumbnailInfo;
  readonly className?: string;
  /** `cover` crops into a fixed card; `contain` (default) shows the whole page. */
  readonly fit?: "contain" | "cover";
  /** Keep the thumbnail's own aspect ratio (default) or fill a sized parent. */
  readonly sizing?: "intrinsic" | "fill";
  /** Called once if the thumbnail itself fails, so callers can fall back. */
  readonly onError?: () => void;
  /** Layered on top, e.g. the full-resolution preview fading in. */
  readonly children?: ReactNode;
}

/**
 * Paints a server-rendered WebP thumbnail inside a box whose size is known
 * before any byte arrives. The image is decorative: the surrounding card or
 * link carries the accessible name.
 */
export function FileThumbnail({
  fileId,
  thumbnail,
  className,
  fit = "contain",
  sizing = "intrinsic",
  onError,
  children,
}: FileThumbnailProps) {
  const [failed, setFailed] = useState(false);
  const style: CSSProperties =
    sizing === "intrinsic" ? { aspectRatio: thumbnailAspect(thumbnail) } : {};
  const classes = ["file-thumbnail", `file-thumbnail--${fit}`, className]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes} style={style} data-sizing={sizing}>
      {failed ? null : (
        <img
          className="file-thumbnail__image"
          src={fileThumbnailUrl(fileId, thumbnail.version)}
          width={thumbnail.width}
          height={thumbnail.height}
          alt=""
          aria-hidden="true"
          decoding="async"
          draggable={false}
          onError={() => {
            setFailed(true);
            onError?.();
          }}
        />
      )}
      {children}
    </span>
  );
}
