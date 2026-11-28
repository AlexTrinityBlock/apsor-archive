/**
 * Pure placement geometry for the floating companion: dock lines, release
 * projection, vertical clamping, size fitting, and the "don't block the
 * reader" rules.
 */
import type { CompanionSize } from "./preference";

export interface Rect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

export type Breakpoint = "phone" | "tablet" | "desktop";

/**
 * Dock lines the companion snaps to. Panel lines sit just inside the chat
 * stream panel (beside the composer); viewport lines hug the window edge.
 */
export type DockSide =
  | "viewport-left"
  | "viewport-right"
  | "panel-left"
  | "panel-right";

export const DOCK_SIDES: readonly DockSide[] = [
  "viewport-left",
  "viewport-right",
  "panel-left",
  "panel-right",
];

export interface SavedPosition {
  readonly side: DockSide;
  /** Top of the box as a fraction of the viewport height. */
  readonly y: number;
}

export interface LayoutContext {
  readonly viewport: { readonly width: number; readonly height: number };
  /** The chat stream panel; null outside chat or before measurement. */
  readonly panel: Rect | null;
  /** The composer dock; the companion never covers it. */
  readonly composer: Rect | null;
  /** Visible part of the reading column. */
  readonly column: Rect | null;
  /**
   * The app's main content region (right of the navigation rail). Viewport
   * dock lines hug its edges so a drop never lands behind the rail.
   */
  readonly content?: Rect | null;
}

export interface BoxSize {
  readonly width: number;
  readonly height: number;
}

export const EDGE_MARGIN = 10;
const TOP_MARGIN = 64;
/** Free space above the figure for floating effects (?, zZ, sparkles). */
export const FIGURE_HEADROOM = 20;

export function breakpointFor(width: number): Breakpoint {
  if (width < 620) {
    return "phone";
  }
  return width < 980 ? "tablet" : "desktop";
}

/** The art's intrinsic frame size; the figure never renders larger than this. */
export const INTRINSIC_FIGURE: BoxSize = { width: 384, height: 576 };

/** Compact figure size (without headroom) per breakpoint, 2:3 like the art. */
export function figureSize(breakpoint: Breakpoint): BoxSize {
  switch (breakpoint) {
    case "phone":
      return { width: 96, height: 144 };
    case "tablet":
      return { width: 124, height: 186 };
    default:
      return { width: 148, height: 222 };
  }
}

/** Target figure size for a size setting before it is fitted to the screen. */
export function targetFigure(size: CompanionSize, breakpoint: Breakpoint): BoxSize {
  if (size === "compact") {
    return figureSize(breakpoint);
  }
  if (breakpoint === "phone") {
    return size === "full" ? { width: 160, height: 240 } : { width: 124, height: 186 };
  }
  return size === "full" ? INTRINSIC_FIGURE : { width: 240, height: 360 };
}

/**
 * The widest free gutter beside the reading column inside the main content,
 * or the whole content width when there is no column.
 */
export function gutterWidth(context: LayoutContext): number {
  const content = context.content ?? null;
  const contentLeft = content?.left ?? 0;
  const contentRight =
    content === null ? context.viewport.width : content.left + content.width;
  const column = context.column;
  if (column === null) {
    return Math.max(0, contentRight - contentLeft - 2 * EDGE_MARGIN);
  }
  const leftGutter = column.left - contentLeft;
  const rightGutter = contentRight - (column.left + column.width);
  return Math.max(0, Math.max(leftGutter, rightGutter) - 2 * EDGE_MARGIN);
}

/**
 * Fit a size setting to the screen: scale the target down (never up) so it
 * fits the viewport height and the free gutter, but never below the compact
 * size. When even compact does not fit the gutter, avoidance makes it peek.
 */
export function figureSizeFor(
  size: CompanionSize,
  breakpoint: Breakpoint,
  context: LayoutContext,
): BoxSize {
  const target = targetFigure(size, breakpoint);
  const floor = figureSize(breakpoint);
  if (size === "compact") {
    return floor;
  }
  const maxHeight = context.viewport.height - TOP_MARGIN - EDGE_MARGIN - FIGURE_HEADROOM;
  const maxWidth = breakpoint === "phone" ? target.width : gutterWidth(context);
  const scale = Math.min(1, maxHeight / target.height, maxWidth / target.width);
  const height = Math.max(floor.height, Math.floor(target.height * scale));
  return { width: Math.round((height * 2) / 3), height };
}

export function boxSize(breakpoint: Breakpoint): BoxSize {
  const figure = figureSize(breakpoint);
  return { width: figure.width, height: figure.height + FIGURE_HEADROOM };
}

/** Box (figure plus headroom) for a size setting in the current layout. */
export function boxSizeFor(
  size: CompanionSize,
  breakpoint: Breakpoint,
  context: LayoutContext,
): BoxSize {
  const figure = figureSizeFor(size, breakpoint, context);
  return { width: figure.width, height: figure.height + FIGURE_HEADROOM };
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

/** Left coordinate of a dock line for a box of the given width. */
export function dockX(side: DockSide, context: LayoutContext, width: number): number {
  const content = context.content ?? null;
  const minX = content === null ? EDGE_MARGIN : Math.max(EDGE_MARGIN, content.left + EDGE_MARGIN);
  const rightEdge =
    content === null
      ? context.viewport.width
      : Math.min(context.viewport.width, content.left + content.width);
  const maxX = Math.max(minX, rightEdge - width - EDGE_MARGIN);
  const panel = context.panel;
  switch (side) {
    case "viewport-left":
      return minX;
    case "viewport-right":
      return maxX;
    case "panel-left":
      return panel === null ? minX : clamp(panel.left + EDGE_MARGIN, minX, maxX);
    case "panel-right":
      return panel === null
        ? maxX
        : clamp(panel.left + panel.width - width - EDGE_MARGIN, minX, maxX);
  }
}

/** Keep the box on screen and out of the composer's vertical band. */
export function clampTop(top: number, context: LayoutContext, box: BoxSize, left: number): number {
  let maxTop = context.viewport.height - box.height - EDGE_MARGIN;
  const composer = context.composer;
  if (composer !== null) {
    const overlapsX =
      left < composer.left + composer.width && left + box.width > composer.left;
    if (overlapsX) {
      maxTop = Math.min(maxTop, composer.top - box.height - 6);
    }
  }
  return clamp(top, Math.min(TOP_MARGIN, maxTop), maxTop);
}

export function defaultPosition(
  breakpoint: Breakpoint,
  context: LayoutContext,
  box: BoxSize = boxSize(breakpoint),
): SavedPosition {
  const side: DockSide = breakpoint === "phone" ? "viewport-right" : "panel-right";
  const bottom = context.composer?.top ?? context.viewport.height;
  const top = bottom - box.height - 8;
  return { side, y: clamp(top / Math.max(1, context.viewport.height), 0, 1) };
}

/** Concrete box rectangle for a saved position in the current layout. */
export function resolveBox(
  position: SavedPosition,
  context: LayoutContext,
  box: BoxSize,
): Rect {
  const left = dockX(position.side, context, box.width);
  const top = clampTop(position.y * context.viewport.height, context, box, left);
  return { left, top, width: box.width, height: box.height };
}

/**
 * Where a released drag lands: project the throw a short way along its
 * velocity (px/ms), then snap to the nearest dock line.
 */
export function landingPosition(
  left: number,
  top: number,
  velocity: { readonly x: number; readonly y: number },
  context: LayoutContext,
  box: BoxSize,
  throwMs = 160,
): SavedPosition {
  const projectedX = left + velocity.x * throwMs;
  const projectedY = top + velocity.y * throwMs;
  let best: DockSide = "viewport-right";
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const side of DOCK_SIDES) {
    if (context.panel === null && side.startsWith("panel")) {
      continue;
    }
    const distance = Math.abs(dockX(side, context, box.width) - projectedX);
    if (distance < bestDistance) {
      best = side;
      bestDistance = distance;
    }
  }
  const snappedLeft = dockX(best, context, box.width);
  const snappedTop = clampTop(projectedY, context, box, snappedLeft);
  return { side: best, y: snappedTop / Math.max(1, context.viewport.height) };
}

export function intersectionArea(a: Rect, b: Rect): number {
  const width = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left);
  const height = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top);
  return width > 0 && height > 0 ? width * height : 0;
}

export type Avoidance = "clear" | "peek" | "hidden";

/**
 * Decide how present the companion may be. A modal dialog hides it; covering
 * more than a sliver of the reading column turns it into a peeking,
 * translucent figure until the reader hovers or focuses it.
 */
export function avoidance(
  box: Rect,
  context: LayoutContext,
  dialogOpen: boolean,
  breakpoint: Breakpoint,
): Avoidance {
  if (dialogOpen) {
    return "hidden";
  }
  if (breakpoint === "phone") {
    return "peek";
  }
  const column = context.column;
  if (column === null) {
    return "clear";
  }
  const covered = intersectionArea(box, column) / Math.max(1, box.width * box.height);
  return covered > 0.12 ? "peek" : "clear";
}

/** Whether a dock side hugs the window edge (slide-out peek) or not (shrink). */
export function isViewportSide(side: DockSide): boolean {
  return side === "viewport-left" || side === "viewport-right";
}

export function isLeftSide(side: DockSide): boolean {
  return side === "viewport-left" || side === "panel-left";
}

export function readSavedPosition(value: unknown): SavedPosition | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const side = record.side;
  const y = record.y;
  if (
    typeof side === "string" &&
    (DOCK_SIDES as readonly string[]).includes(side) &&
    typeof y === "number" &&
    Number.isFinite(y)
  ) {
    return { side: side as DockSide, y: clamp(y, 0, 1) };
  }
  return null;
}
