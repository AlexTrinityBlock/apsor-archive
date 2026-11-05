import { useEffect } from "react";

/** Root CSS property carrying the visible viewport height in pixels. */
const VIEWPORT_HEIGHT_PROPERTY = "--app-visual-viewport-height";
/** Root CSS property carrying the visible viewport top offset in pixels. */
const VIEWPORT_TOP_PROPERTY = "--app-visual-viewport-top";

/**
 * Mirror the visual viewport onto the document root.
 *
 * Mobile browsers shrink `visualViewport` when the on-screen keyboard opens
 * while the layout viewport, `100dvh`, and fixed overlays keep their full
 * height. Publishing the visible height and offset lets a full-screen editor
 * end above the keyboard instead of underneath it.
 */
export function useVisualViewport(): void {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }
    const root = document.documentElement;
    const sync = () => {
      root.style.setProperty(
        VIEWPORT_HEIGHT_PROPERTY,
        `${viewport.height}px`,
      );
      root.style.setProperty(
        VIEWPORT_TOP_PROPERTY,
        `${Math.max(0, viewport.offsetTop)}px`,
      );
    };
    sync();
    viewport.addEventListener("resize", sync);
    viewport.addEventListener("scroll", sync);
    return () => {
      viewport.removeEventListener("resize", sync);
      viewport.removeEventListener("scroll", sync);
      root.style.removeProperty(VIEWPORT_HEIGHT_PROPERTY);
      root.style.removeProperty(VIEWPORT_TOP_PROPERTY);
    };
  }, []);
}
