import { useEffect } from "react";

/** Root CSS property carrying the visible viewport height in pixels. */
const VIEWPORT_HEIGHT_PROPERTY = "--app-visual-viewport-height";
/** Root CSS property carrying the visible viewport top offset in pixels. */
const VIEWPORT_TOP_PROPERTY = "--app-visual-viewport-top";
/** Root attribute set while an on-screen keyboard covers part of the layout. */
const KEYBOARD_ATTRIBUTE = "data-visual-keyboard";

/**
 * Covered height, in CSS pixels, that enters the keyboard-open state. Android
 * URL bars change the viewport by roughly 56-80 px; even a landscape phone
 * keyboard covers about 120 px.
 */
export const KEYBOARD_OPEN_INSET = 120;
/**
 * Covered height that leaves the keyboard-open state. Keeping this below the
 * open threshold adds hysteresis, so animation frames near the boundary cannot
 * flap the shell height.
 */
export const KEYBOARD_CLOSE_INSET = 80;

export interface VisualViewportMetrics {
  readonly layoutHeight: number;
  readonly visualHeight: number;
  readonly visualTop: number;
  readonly scale: number;
}

/**
 * Decide whether an on-screen keyboard obscures part of the layout viewport.
 *
 * `layoutHeight` is the layout viewport height (the larger of
 * `window.innerHeight` and the document client height). iOS Safari and current
 * Android Chrome leave it at the pre-keyboard size and shrink only the visual
 * viewport, so the covered band is the keyboard. Pinch zoom also shrinks the
 * visual viewport; a non-unit scale is therefore never treated as a keyboard.
 * Safari may pan the visual viewport down to keep a focused field visible, which
 * is the second signal.
 */
export function isKeyboardOpen(
  previous: boolean,
  metrics: VisualViewportMetrics,
): boolean {
  const { layoutHeight, visualHeight, visualTop, scale } = metrics;
  if (
    !Number.isFinite(layoutHeight) ||
    !Number.isFinite(visualHeight) ||
    layoutHeight <= 0 ||
    visualHeight <= 0 ||
    Math.abs(scale - 1) > 0.01
  ) {
    return false;
  }
  const covered = Math.max(layoutHeight - visualHeight, visualTop, 0);
  return previous
    ? covered >= KEYBOARD_CLOSE_INSET
    : covered >= KEYBOARD_OPEN_INSET;
}

/** Read one coherent visual/layout viewport snapshot. */
function readMetrics(viewport: VisualViewport): VisualViewportMetrics {
  return {
    // The layout viewport is whichever of these still reports the pre-keyboard
    // height; a browser that shrinks both already resizes `100dvh` for us.
    layoutHeight: Math.max(
      window.innerHeight,
      document.documentElement.clientHeight,
    ),
    visualHeight: viewport.height,
    visualTop: Math.max(0, viewport.offsetTop),
    scale: viewport.scale,
  };
}

/**
 * Mirror the visual viewport onto the document root.
 *
 * Mobile browsers shrink `visualViewport` when the on-screen keyboard opens
 * while the layout viewport, `100dvh`, and fixed overlays keep their full
 * height. Publishing the visible height and offset lets the mobile shell and
 * full-screen editor surfaces end above the keyboard instead of underneath it.
 * The `data-visual-keyboard` attribute tells the shell when it must follow the
 * visible band, so ordinary URL-bar resizing keeps using `100dvh`.
 *
 * `AppShell` owns the only listener; descendants consume the root variables and
 * must not mount the hook again, or unmounting one surface would clear the
 * values another surface still needs.
 */
export function useVisualViewport(): void {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }
    const root = document.documentElement;
    let keyboardOpen = false;
    const sync = () => {
      const top = Math.max(0, viewport.offsetTop);
      root.style.setProperty(
        VIEWPORT_HEIGHT_PROPERTY,
        `${viewport.height}px`,
      );
      root.style.setProperty(VIEWPORT_TOP_PROPERTY, `${top}px`);
      const nextKeyboardOpen = isKeyboardOpen(
        keyboardOpen,
        readMetrics(viewport),
      );
      if (nextKeyboardOpen !== keyboardOpen) {
        keyboardOpen = nextKeyboardOpen;
        if (keyboardOpen) {
          root.setAttribute(KEYBOARD_ATTRIBUTE, "open");
        } else {
          root.removeAttribute(KEYBOARD_ATTRIBUTE);
        }
      }
    };
    sync();
    viewport.addEventListener("resize", sync);
    viewport.addEventListener("scroll", sync);
    // URL-bar changes can resize the layout viewport without a visual viewport
    // event; re-read the pair so the keyboard threshold sees both values.
    window.addEventListener("resize", sync);
    return () => {
      viewport.removeEventListener("resize", sync);
      viewport.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      root.style.removeProperty(VIEWPORT_HEIGHT_PROPERTY);
      root.style.removeProperty(VIEWPORT_TOP_PROPERTY);
      root.removeAttribute(KEYBOARD_ATTRIBUTE);
    };
  }, []);
}
