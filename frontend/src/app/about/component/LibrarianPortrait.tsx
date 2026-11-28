import { useState } from "react";

interface LibrarianPortraitProps {
  /** Preset companion id, e.g. `vellum`; resolves to `/companions/<id>/portrait.avif`. */
  readonly id: string;
  readonly alt: string;
  readonly size: number;
  readonly className?: string;
}

/**
 * A librarian portrait from the built-in companion presets. The image has a
 * fixed box so the page never shifts; if the asset is missing (for example in
 * a build without the companion art), a quiet monogram takes its place.
 */
export function LibrarianPortrait({ id, alt, size, className }: LibrarianPortraitProps) {
  const [failed, setFailed] = useState(false);
  const classes = ["about-portrait", className].filter(Boolean).join(" ");

  if (failed) {
    return (
      <span
        className={`${classes} about-portrait--fallback`}
        style={{ width: size, height: size }}
        role="img"
        aria-label={alt}
      >
        <span aria-hidden="true">{id.charAt(0).toUpperCase()}</span>
      </span>
    );
  }

  return (
    <img
      className={classes}
      src={`/companions/${id}/portrait.avif`}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
