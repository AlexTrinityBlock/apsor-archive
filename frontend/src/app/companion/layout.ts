/**
 * Pure placement geometry for the floating companion: dock lines, release
 * projection, vertical clamping, size fitting, and the "don't block the
 * reader" rules.
 */
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
  /**
   * Bottom of the box (the figure's feet) as a fraction of the viewport
   * height. When present it wins over `y`, so resizing keeps the feet still.
   * Older saved positions have only `y`.
   */
  readonly feet?: number;
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
  /**
   * The part of the layout viewport the reader can actually see, from the
   * visual viewport. An on-screen keyboard shrinks it without resizing the
   * layout viewport, so placement keeps to this band while positions stay
   * stored against the stable layout viewport.
   */
  readonly visible?: {
    readonly top: number;
    readonly bottom: number;
    readonly left?: number;
    readonly right?: number;
  } | null;
}

export interface BoxSize {
  readonly width: number;
  readonly height: number;
}

export const EDGE_MARGIN = 10;
export const TOP_MARGIN = 64;
/** Free space above the figure for floating effects (?, zZ, sparkles). */
export const FIGURE_HEADROOM = 20;

/** Visible band (layout-viewport coordinates); the whole viewport by default. */
export interface VisibleBand {
  readonly top: number;
  readonly bottom: number;
  readonly left: number;
  readonly right: number;
}

export function visibleBand(context: LayoutContext): VisibleBand {
  const visible = context.visible ?? null;
  const { width, height } = context.viewport;
  if (visible === null) {
    return { top: 0, bottom: height, left: 0, right: width };
  }
  return {
    top: Math.max(0, visible.top),
    bottom: Math.min(height, visible.bottom),
    left: Math.max(0, visible.left ?? 0),
    right: Math.min(width, visible.right ?? width),
  };
}

/** An on-screen keyboard (or similar) is eating a large part of the viewport. */
export function keyboardOpen(context: LayoutContext): boolean {
  const band = visibleBand(context);
  return context.viewport.height - (band.bottom - band.top) > 120;
}

/** Small margin kept from the visible top while the keyboard is open. */
export const KEYBOARD_TOP_MARGIN = 8;

/**
 * Highest the head may rise. Normally below the top bar; with the keyboard
 * open the free space is precious, so the figure may overlap the header and
 * use the band from just below its visible top.
 */
export function topLimit(context: LayoutContext): number {
  const band = visibleBand(context);
  return band.top + (keyboardOpen(context) ? KEYBOARD_TOP_MARGIN : TOP_MARGIN);
}

/** The line the companion's feet rest on: above the composer and the keyboard. */
export function feetLine(context: LayoutContext): number {
  const bottom = visibleBand(context).bottom;
  const composerTop = context.composer?.top ?? Number.POSITIVE_INFINITY;
  return Math.min(composerTop, bottom) - 6;
}

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

/** Compact box (figure plus headroom); sized boxes come from `size.ts`. */
export function boxSize(breakpoint: Breakpoint): BoxSize {
  const figure = figureSize(breakpoint);
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
  const band = visibleBand(context);
  const minX = Math.max(
    band.left + EDGE_MARGIN,
    content === null ? EDGE_MARGIN : content.left + EDGE_MARGIN,
  );
  const rightEdge = Math.min(
    band.right,
    content === null ? context.viewport.width : content.left + content.width,
  );
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
  let maxTop = visibleBand(context).bottom - box.height - EDGE_MARGIN;
  const composer = context.composer;
  if (composer !== null) {
    const overlapsX =
      left < composer.left + composer.width && left + box.width > composer.left;
    if (overlapsX) {
      maxTop = Math.min(maxTop, composer.top - box.height - 6);
    }
  }
  const minTop = topLimit(context);
  // A box taller than the band keeps its head on screen rather than its feet.
  return maxTop < minTop ? minTop : clamp(top, minTop, maxTop);
}

export function defaultPosition(
  breakpoint: Breakpoint,
  context: LayoutContext,
  box: BoxSize = boxSize(breakpoint),
): SavedPosition {
  const side: DockSide = breakpoint === "phone" ? "viewport-right" : "panel-right";
  return positionAt(side, feetLine(context) - 2 - box.height, box, context);
}

/** Saved position for a box whose top edge is at `top` on a dock side. */
export function positionAt(
  side: DockSide,
  top: number,
  box: BoxSize,
  context: LayoutContext,
): SavedPosition {
  const height = Math.max(1, context.viewport.height);
  return { side, y: clamp(top / height, 0, 1), feet: clamp((top + box.height) / height, 0, 1) };
}

/** Concrete box rectangle for a saved position in the current layout. */
export function resolveBox(
  position: SavedPosition,
  context: LayoutContext,
  box: BoxSize,
): Rect {
  const left = dockX(position.side, context, box.width);
  const wanted =
    position.feet === undefined
      ? position.y * context.viewport.height
      : position.feet * context.viewport.height - box.height;
  const top = clampTop(wanted, context, box, left);
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
  return positionAt(best, snappedTop, box, context);
}

export function intersectionArea(a: Rect, b: Rect): number {
  const width = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left);
  const height = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top);
  return width > 0 && height > 0 ? width * height : 0;
}

/**
 * - clear: show the figure.
 * - peek: shrink in place (panel docks) until hovered or focused.
 * - retract: tuck away as a bookmark tab at the window edge.
 * - hidden: a modal dialog is open.
 */
export type Avoidance = "clear" | "peek" | "retract" | "hidden";

/** Whether even the smallest figure fits between the top bar and the feet line. */
export function hasRoom(context: LayoutContext, minFigureHeight: number): boolean {
  return feetLine(context) - topLimit(context) - FIGURE_HEADROOM >= minFigureHeight;
}

/**
 * Decide how present the companion may be. A modal dialog hides it. On a
 * phone the figure stays visible at its fitted size (the reader tucks it away
 * explicitly) and only retracts when there is no room at all. Elsewhere,
 * covering more than a sliver of the reading column retracts a window-edge
 * figure into a bookmark tab and shrinks a panel-docked one.
 */
export function avoidance(
  box: Rect,
  context: LayoutContext,
  dialogOpen: boolean,
  breakpoint: Breakpoint,
  side: DockSide = "panel-right",
): Avoidance {
  if (dialogOpen) {
    return "hidden";
  }
  // With the keyboard open, never slide, shrink or tuck away on its own: fit in
  // the free space (the reader may still collapse it explicitly).
  if (keyboardOpen(context)) {
    return "clear";
  }
  if (!hasRoom(context, figureSize(breakpoint).height)) {
    return "retract";
  }
  if (breakpoint === "phone") {
    return "clear";
  }
  const column = context.column;
  if (column === null) {
    return "clear";
  }
  const covered = intersectionArea(box, column) / Math.max(1, box.width * box.height);
  if (covered <= 0.12) {
    return "clear";
  }
  return isViewportSide(side) ? "retract" : "peek";
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
    const feet = record.feet;
    return typeof feet === "number" && Number.isFinite(feet)
      ? { side: side as DockSide, y: clamp(y, 0, 1), feet: clamp(feet, 0, 1) }
      : { side: side as DockSide, y: clamp(y, 0, 1) };
  }
  return null;
}

/** Move a saved position vertically by a fraction of the viewport height. */
export function shiftPosition(position: SavedPosition, delta: number): SavedPosition {
  const y = clamp(position.y + delta, 0, 1);
  return position.feet === undefined
    ? { side: position.side, y }
    : { side: position.side, y, feet: clamp(position.feet + delta, 0, 1) };
}

/**
 * Keep the feet still when the box changes size. If the head would rise past
 * the top margin, the feet move down instead, but never into the composer.
 */
export function anchorFeet(
  position: SavedPosition,
  context: LayoutContext,
  from: Rect,
  next: BoxSize,
): SavedPosition {
  const baseline = feetLine(context);
  let feet = from.top + from.height;
  if (feet - next.height < topLimit(context)) {
    feet = Math.min(topLimit(context) + next.height, baseline);
  }
  return positionAt(position.side, feet - next.height, next, context);
}

export interface PeekGeometry {
  /** Scale for the shrink peek (panel docks). */
  readonly scale: number;
  /** Fraction of the stage slid off-screen for the slide peek (window edges). */
  readonly slide: number;
}

/** Peek amounts that leave a large figure no wider than the free gutter. */
export function peekGeometry(box: BoxSize, context: LayoutContext): PeekGeometry {
  const ratio = gutterWidth(context) / Math.max(1, box.width);
  // Never smaller than this: a peeking figure must stay recognisable.
  return { scale: clamp(ratio, 0.45, 0.6), slide: clamp(1 - ratio, 0.58, 0.82) };
}

export interface BookmarkPlacement {
  readonly top: number;
  /** Distance from the layout viewport's left edge (left-docked tab). */
  readonly left: number;
  /** Distance from the layout viewport's right edge (right-docked tab). */
  readonly right: number;
}

/**
 * Where the collapsed bookmark tab sits: at the figure's height, but always
 * fully inside the visible band, hugging the visible edge (not the layout
 * edge, which can be off-screen while zoomed or with a keyboard open).
 */
export function bookmarkTop(
  wantedTop: number,
  tabHeight: number,
  context: LayoutContext,
): BookmarkPlacement {
  const band = visibleBand(context);
  const minTop = band.top + TOP_MARGIN;
  const maxTop = band.bottom - tabHeight - EDGE_MARGIN;
  const top = maxTop < minTop ? Math.max(band.top, maxTop) : clamp(wantedTop, minTop, maxTop);
  return {
    top,
    left: band.left,
    right: Math.max(0, context.viewport.width - band.right),
  };
}
