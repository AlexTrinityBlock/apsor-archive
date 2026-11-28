/**
 * Pure sizing for the companion figure. Size is one continuous "level" from 0
 * (Compact) to 1 (Full). Full means "as large as this screen allows, up to the
 * art's native 384×576", so the three presets stay distinct on every screen.
 * Heights are interpolated logarithmically so a pinch ratio or a wheel notch
 * feels the same at any size. Compact, Medium and Full act as magnets.
 */
import {
  FIGURE_HEADROOM,
  INTRINSIC_FIGURE,
  feetLine,
  figureSize,
  gutterWidth,
  keyboardOpen,
  topLimit,
  type BoxSize,
  type Breakpoint,
  type LayoutContext,
} from "./layout";
import type { CompanionSize } from "./preference";

/** The art's intrinsic frame size (2:3); the figure never renders larger. */
export const ART: BoxSize = INTRINSIC_FIGURE;

export const SIZE_LEVELS: Readonly<Record<CompanionSize, number>> = {
  compact: 0,
  medium: 0.5,
  full: 1,
};

export interface SizeRange {
  /** Compact height for the breakpoint. */
  readonly minHeight: number;
  /** Full height: the largest the screen allows, at most the art height. */
  readonly maxHeight: number;
  /** Level at which the figure just fits beside the chat, when useful. */
  readonly fitLevel: number | null;
  /** False when Compact and Full are (almost) the same size. */
  readonly resizable: boolean;
}

export type DetentId = CompanionSize | "fit";

export interface Detent {
  readonly id: DetentId;
  readonly level: number;
}

/** A magnet engages within this distance and lets go beyond the next one. */
const SNAP_ENGAGE = 0.05;
const SNAP_RELEASE = 0.08;
/** Past the ends the figure stretches with this resistance, up to the cap. */
const RUBBER_RESISTANCE = 0.25;
const RUBBER_CAP = 0.12;
/** Keyboard step on the 0..1 level. */
export const LEVEL_STEP = 0.1;
const WHEEL_FACTOR = 0.0018;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** The line the companion's feet rest on: above the composer and keyboard. */
export function baselineY(context: LayoutContext): number {
  return feetLine(context);
}

function contentWidth(context: LayoutContext): number {
  const content = context.content ?? null;
  return content === null ? context.viewport.width : content.width;
}

export function heightForLevel(level: number, range: SizeRange): number {
  if (range.maxHeight <= range.minHeight) {
    return range.minHeight;
  }
  return range.minHeight * (range.maxHeight / range.minHeight) ** level;
}

/** Inverse of {@link heightForLevel}; not clamped, so drags can overshoot. */
export function levelForHeight(height: number, range: SizeRange): number {
  if (range.maxHeight <= range.minHeight || height <= 0) {
    return 0;
  }
  return Math.log(height / range.minHeight) / Math.log(range.maxHeight / range.minHeight);
}

export function sizeRange(breakpoint: Breakpoint, context: LayoutContext): SizeRange {
  const minHeight = figureSize(breakpoint).height;
  // Derived every layout pass from the visible band, never persisted: an
  // on-screen keyboard narrows it, and closing the keyboard restores it, while
  // the user's chosen level stays the same.
  const heightCap = baselineY(context) - topLimit(context) - FIGURE_HEADROOM;
  const widthCap = contentWidth(context) * (breakpoint === "phone" ? 0.5 : 0.4);
  const maxHeight = Math.floor(
    Math.max(minHeight, Math.min(ART.height, heightCap, widthCap * 1.5)),
  );
  const range: SizeRange = {
    minHeight,
    maxHeight,
    fitLevel: null,
    resizable: maxHeight >= minHeight * 1.08,
  };
  if (!range.resizable) {
    return range;
  }
  const fitHeight = gutterWidth(context) * 1.5;
  const fit = levelForHeight(fitHeight, range);
  const useful = fit > 0.08 && fit < 0.92 && Math.abs(fit - SIZE_LEVELS.medium) >= 0.08;
  return { ...range, fitLevel: useful ? fit : null };
}

/** Figure size (2:3) for a level, clamped to the range. */
export function figureForLevel(level: number, range: SizeRange): BoxSize {
  const height = Math.round(heightForLevel(clamp(level, 0, 1), range));
  return { width: Math.round((height * 2) / 3), height };
}

/** Figure size for a level without clamping (live overshoot preview). */
export function figureForDisplayLevel(level: number, range: SizeRange): BoxSize {
  const height = Math.round(heightForLevel(level, range));
  return { width: Math.round((height * 2) / 3), height };
}

/** Box (figure plus headroom for floating effects). */
export function boxForFigure(figure: BoxSize): BoxSize {
  return { width: figure.width, height: figure.height + FIGURE_HEADROOM };
}

export function detentsFor(range: SizeRange): readonly Detent[] {
  const detents: Detent[] = [
    { id: "compact", level: SIZE_LEVELS.compact },
    { id: "medium", level: SIZE_LEVELS.medium },
    { id: "full", level: SIZE_LEVELS.full },
  ];
  if (range.fitLevel !== null) {
    detents.push({ id: "fit", level: range.fitLevel });
  }
  return detents.sort((a, b) => a.level - b.level);
}

export interface Magnetized {
  readonly level: number;
  readonly snapped: Detent | null;
}

/**
 * Pull a level onto a nearby magnet. A held magnet keeps the level until it
 * moves past the release distance, so the figure doesn't flicker at the edge.
 */
export function magnetize(
  raw: number,
  detents: readonly Detent[],
  held: Detent | null,
): Magnetized {
  if (held !== null && Math.abs(raw - held.level) <= SNAP_RELEASE) {
    return { level: held.level, snapped: held };
  }
  let best: Detent | null = null;
  for (const detent of detents) {
    const distance = Math.abs(raw - detent.level);
    if (distance <= SNAP_ENGAGE && (best === null || distance < Math.abs(raw - best.level))) {
      best = detent;
    }
  }
  return best === null ? { level: raw, snapped: null } : { level: best.level, snapped: best };
}

/** Beyond 0 or 1 the figure only stretches a little, then stops. */
export function rubberBand(raw: number): number {
  if (raw > 1) {
    return 1 + Math.min(RUBBER_CAP, (raw - 1) * RUBBER_RESISTANCE);
  }
  if (raw < 0) {
    return Math.max(-RUBBER_CAP, raw * RUBBER_RESISTANCE);
  }
  return raw;
}

/**
 * Turn a raw gesture level into what is shown: rubber band past the ends,
 * magnets inside. With `rubber` off (reduced motion) the ends are hard stops.
 */
export function displayLevel(
  raw: number,
  detents: readonly Detent[],
  held: Detent | null,
  rubber: boolean,
): Magnetized {
  if (raw > 1 || raw < 0) {
    const bound = detents.find((detent) => detent.level === (raw > 1 ? 1 : 0)) ?? null;
    return { level: rubber ? rubberBand(raw) : clamp(raw, 0, 1), snapped: bound };
  }
  return magnetize(raw, detents, held);
}

export function settleLevel(display: number): number {
  return clamp(display, 0, 1);
}

/**
 * Corner-grip drag: project the pointer delta onto the 2:3 diagonal so the
 * corner follows the pointer. Moving up and inward grows the figure.
 */
export function gripLevel(
  startHeight: number,
  range: SizeRange,
  dx: number,
  dy: number,
  dockedLeft: boolean,
): number {
  const inward = dockedLeft ? dx : -dx;
  const height = startHeight + ((2 * inward + 3 * -dy) * 3) / 13;
  return levelForHeight(Math.max(1, height), range);
}

/** Pinch: height follows the finger distance ratio. */
export function pinchLevel(startHeight: number, range: SizeRange, ratio: number): number {
  return levelForHeight(Math.max(1, startHeight * ratio), range);
}

/** Ctrl/⌘+wheel: one mouse notch is about 16%; clamped to the range. */
export function wheelLevel(
  level: number,
  range: SizeRange,
  deltaY: number,
  deltaMode: number,
  viewportHeight: number,
): number {
  let pixels = deltaY;
  if (deltaMode === 1) {
    pixels = deltaY * 16;
  } else if (deltaMode === 2) {
    pixels = deltaY * viewportHeight;
  }
  const height = heightForLevel(level, range) * Math.exp(-pixels * WHEEL_FACTOR);
  return clamp(levelForHeight(height, range), 0, 1);
}

/** Keyboard step, or a jump to the next magnet strictly beyond the level. */
export function stepLevel(
  level: number,
  direction: 1 | -1,
  jump: boolean,
  detents: readonly Detent[],
): number {
  if (!jump) {
    return clamp(Math.round((level + direction * LEVEL_STEP) * 1000) / 1000, 0, 1);
  }
  const ordered = [...detents].sort((a, b) => a.level - b.level);
  if (direction > 0) {
    return ordered.find((detent) => detent.level > level + 0.001)?.level ?? 1;
  }
  return [...ordered].reverse().find((detent) => detent.level < level - 0.001)?.level ?? 0;
}

export interface FullToggle {
  readonly level: number;
  readonly lastNonFull: number | null;
}

/** Double-click/tap: Full, or back to the last size that wasn't Full. */
export function toggleFull(level: number, lastNonFull: number | null): FullToggle {
  if (level >= 0.999) {
    return { level: lastNonFull ?? SIZE_LEVELS.medium, lastNonFull };
  }
  return { level: 1, lastNonFull: level };
}

export function presetForLevel(level: number): CompanionSize {
  if (level < 0.25) {
    return "compact";
  }
  return level < 0.75 ? "medium" : "full";
}

/** The stored scale wins; otherwise the preset's level. */
export function effectiveLevel(scale: number | null, size: CompanionSize): number {
  return scale ?? SIZE_LEVELS[size];
}

export function readScale(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.round(clamp(value, 0, 1) * 1000) / 1000;
}

export interface Readout {
  /** Translation key of the snapped magnet, or null for a free size. */
  readonly labelKey: `companion.size.${DetentId}` | null;
  /** Height as a percentage of the native art height. */
  readonly percent: number;
}

export function readoutFor(level: number, snapped: Detent | null, range: SizeRange): Readout {
  return {
    labelKey: snapped === null ? null : `companion.size.${snapped.id}`,
    percent: Math.round((heightForLevel(level, range) / ART.height) * 100),
  };
}

/** A fixed range for previews outside the chat (settings page). */
export function previewRange(maxHeight: number): SizeRange {
  const minHeight = figureSize("desktop").height;
  return {
    minHeight,
    maxHeight: Math.max(minHeight, Math.min(ART.height, maxHeight)),
    fitLevel: null,
    resizable: true,
  };
}

/** Smallest figure that still reads as a person (2:3), on any screen. */
export const READABLE_FIGURE: BoxSize = { width: 96, height: 144 };

export interface FittedFigure {
  /** What to draw this layout pass; never persisted. */
  readonly figure: BoxSize;
  /** False when not even a readable figure fits: show the bookmark tab. */
  readonly room: boolean;
}

/**
 * Fit the user's chosen figure into the free space of this layout pass.
 * The chosen size (a persisted level) is untouched; this only derives what is
 * drawn. Height is already bounded by the visible band through
 * {@link sizeRange}. On wider screens the figure also shrinks to the free
 * gutter beside the reading column so it never covers messages, but never
 * below a readable size: with less room than that it tucks into a bookmark.
 * Phones and an open keyboard keep the moderate, height-bounded size.
 */
export function fittedFigure(
  chosen: BoxSize,
  breakpoint: Breakpoint,
  context: LayoutContext,
): FittedFigure {
  if (breakpoint === "phone" || keyboardOpen(context) || context.column === null) {
    return { figure: chosen, room: true };
  }
  const gutter = gutterWidth(context);
  if (chosen.width <= gutter) {
    return { figure: chosen, room: true };
  }
  const width = Math.floor(gutter);
  if (width < READABLE_FIGURE.width) {
    return { figure: chosen, room: false };
  }
  return { figure: { width, height: Math.round(width * 1.5) }, room: true };
}
