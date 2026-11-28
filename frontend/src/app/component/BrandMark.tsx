import { useState } from "react";

import { TreeMark } from "./TreeMark";

interface BrandMarkProps {
  readonly size: number;
}

/**
 * The app's brand mark: the flagship librarian's compressed head portrait
 * (`/icon-192.png`, the same art as the favicon). Decorative — the visible
 * product name beside it is the accessible label. Falls back to the older
 * tree mark if the icon cannot load, so the shell never shows a broken image.
 */
export function BrandMark({ size }: BrandMarkProps) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <TreeMark size={size} />;
  }
  return (
    <img
      className="brand-mark"
      src="/icon-192.png"
      alt=""
      width={size}
      height={size}
      decoding="async"
      draggable={false}
      onError={() => setFailed(true)}
    />
  );
}
