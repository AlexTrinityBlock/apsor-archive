// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import type { LayoutContext } from "./layout";
import {
  ART,
  detentsFor,
  displayLevel,
  effectiveLevel,
  figureForLevel,
  fittedFigure,
  READABLE_FIGURE,
  gripLevel,
  heightForLevel,
  levelForHeight,
  magnetize,
  pinchLevel,
  presetForLevel,
  readScale,
  readoutFor,
  rubberBand,
  sizeRange,
  stepLevel,
  toggleFull,
  wheelLevel,
  type Detent,
  type SizeRange,
} from "./size";

const desktop: LayoutContext = {
  viewport: { width: 1280, height: 800 },
  panel: { left: 230, top: 60, width: 1050, height: 740 },
  composer: { left: 250, top: 700, width: 1010, height: 90 },
  column: { left: 305, top: 80, width: 900, height: 600 },
  content: { left: 230, top: 0, width: 1050, height: 800 },
};

const phone: LayoutContext = {
  viewport: { width: 390, height: 844 },
  panel: { left: 0, top: 56, width: 390, height: 788 },
  composer: { left: 0, top: 740, width: 390, height: 100 },
  column: { left: 12, top: 60, width: 366, height: 660 },
  content: { left: 0, top: 0, width: 390, height: 844 },
};

const DESKTOP_RANGE: SizeRange = { minHeight: 222, maxHeight: 576, fitLevel: null, resizable: true };

describe("size range", () => {
  test("desktop spans compact to the native art height", () => {
    const range = sizeRange("desktop", desktop);
    expect(range.minHeight).toBe(222);
    expect(range.maxHeight).toBe(ART.height);
    expect(range.resizable).toBe(true);
  });

  test("phones are capped by width", () => {
    const range = sizeRange("phone", phone);
    expect(range.minHeight).toBe(144);
    expect(range.maxHeight).toBe(292);
  });

  test("short windows are capped by height", () => {
    const short = { ...desktop, viewport: { width: 1280, height: 560 }, composer: null };
    const range = sizeRange("desktop", short);
    expect(range.maxHeight).toBe(560 - 6 - 64 - 20);
  });

  test("no room means not resizable", () => {
    const tiny = { ...desktop, viewport: { width: 1280, height: 310 }, composer: null };
    expect(sizeRange("desktop", tiny).resizable).toBe(false);
  });
});

describe("level ↔ height", () => {
  test("log interpolation between the ends", () => {
    expect(heightForLevel(0, DESKTOP_RANGE)).toBeCloseTo(222, 6);
    expect(heightForLevel(1, DESKTOP_RANGE)).toBeCloseTo(576, 6);
    expect(heightForLevel(0.5, DESKTOP_RANGE)).toBeCloseTo(Math.sqrt(222 * 576), 6);
  });

  test("levelForHeight is the inverse", () => {
    for (const level of [0, 0.2, 0.5, 0.83, 1]) {
      expect(levelForHeight(heightForLevel(level, DESKTOP_RANGE), DESKTOP_RANGE)).toBeCloseTo(level, 9);
    }
  });

  test("figures keep 2:3", () => {
    const figure = figureForLevel(0.5, DESKTOP_RANGE);
    expect(figure.height).toBe(358);
    expect(figure.width).toBe(Math.round((358 * 2) / 3));
  });
});

describe("magnets", () => {
  const detents: readonly Detent[] = detentsFor(DESKTOP_RANGE);
  const medium = detents.find((detent) => detent.id === "medium") ?? null;

  test("engage near a preset and hold with hysteresis", () => {
    expect(magnetize(0.47, detents, null).snapped?.id).toBe("medium");
    expect(magnetize(0.47, detents, null).level).toBe(0.5);
    expect(magnetize(0.43, detents, medium).snapped?.id).toBe("medium");
    expect(magnetize(0.41, detents, medium).snapped).toBeNull();
    expect(magnetize(0.3, detents, null)).toEqual({ level: 0.3, snapped: null });
  });

  test("the fit magnet only appears inside its window", () => {
    expect(detentsFor({ ...DESKTOP_RANGE, fitLevel: 0.3 }).map((d) => d.id)).toContain("fit");
    expect(detentsFor(DESKTOP_RANGE).map((d) => d.id)).not.toContain("fit");
  });

  test("rubber band past the ends", () => {
    expect(rubberBand(5)).toBeCloseTo(1.12, 9);
    expect(rubberBand(-0.2)).toBeCloseTo(-0.05, 9);
    expect(rubberBand(0.4)).toBeCloseTo(0.4, 9);
    expect(displayLevel(1.2, detents, null, true).level).toBeCloseTo(1.05, 9);
    expect(displayLevel(1.2, detents, null, false).level).toBe(1);
    expect(displayLevel(1.2, detents, null, true).snapped?.id).toBe("full");
  });
});

describe("gestures to levels", () => {
  test("grip: up and inward grows, mirrored when docked left", () => {
    const start = heightForLevel(0.5, DESKTOP_RANGE);
    expect(gripLevel(start, DESKTOP_RANGE, -40, -60, false)).toBeGreaterThan(0.5);
    expect(gripLevel(start, DESKTOP_RANGE, 40, 60, false)).toBeLessThan(0.5);
    expect(gripLevel(start, DESKTOP_RANGE, 40, -60, true)).toBeCloseTo(
      gripLevel(start, DESKTOP_RANGE, -40, -60, false),
      9,
    );
  });

  test("pinch: double the distance, double the height", () => {
    const start = 222;
    const level = pinchLevel(start, DESKTOP_RANGE, 2);
    expect(heightForLevel(level, DESKTOP_RANGE)).toBeCloseTo(444, 6);
  });

  test("wheel: negative delta grows; line and page modes normalise", () => {
    expect(wheelLevel(0.5, DESKTOP_RANGE, -100, 0, 800)).toBeGreaterThan(0.5);
    expect(wheelLevel(0.5, DESKTOP_RANGE, 100, 0, 800)).toBeLessThan(0.5);
    expect(wheelLevel(0.5, DESKTOP_RANGE, -3, 1, 800)).toBeCloseTo(
      wheelLevel(0.5, DESKTOP_RANGE, -48, 0, 800),
      9,
    );
    expect(wheelLevel(0.5, DESKTOP_RANGE, -10_000, 0, 800)).toBe(1);
  });

  test("keyboard steps and jumps", () => {
    const detents = detentsFor(DESKTOP_RANGE);
    expect(stepLevel(0.5, 1, false, detents)).toBeCloseTo(0.6, 9);
    expect(stepLevel(0.95, 1, false, detents)).toBe(1);
    expect(stepLevel(0.5, 1, true, detents)).toBe(1);
    expect(stepLevel(0.2, 1, true, detents)).toBe(0.5);
    expect(stepLevel(0.5, -1, true, detents)).toBe(0);
  });

  test("double-click toggles Full and back", () => {
    expect(toggleFull(0.3, null)).toEqual({ level: 1, lastNonFull: 0.3 });
    expect(toggleFull(1, 0.3)).toEqual({ level: 0.3, lastNonFull: 0.3 });
    expect(toggleFull(1, null).level).toBe(0.5);
  });
});

describe("presets and storage", () => {
  test("preset boundaries", () => {
    expect(presetForLevel(0.1)).toBe("compact");
    expect(presetForLevel(0.25)).toBe("medium");
    expect(presetForLevel(0.749)).toBe("medium");
    expect(presetForLevel(0.75)).toBe("full");
  });

  test("a stored scale wins over the preset", () => {
    expect(effectiveLevel(0.33, "full")).toBeCloseTo(0.33, 9);
    expect(effectiveLevel(null, "medium")).toBe(0.5);
    expect(effectiveLevel(null, "compact")).toBe(0);
  });

  test("readScale validates and clamps", () => {
    expect(readScale(Number.NaN)).toBeNull();
    expect(readScale("0.5")).toBeNull();
    expect(readScale(Number.POSITIVE_INFINITY)).toBeNull();
    expect(readScale(1.7)).toBe(1);
    expect(readScale(0.12345)).toBeCloseTo(0.123, 9);
  });

  test("readout names snapped presets, otherwise a percentage", () => {
    const detents = detentsFor(DESKTOP_RANGE);
    const medium = detents.find((detent) => detent.id === "medium") ?? null;
    expect(readoutFor(0.5, medium, DESKTOP_RANGE)).toEqual({
      labelKey: "companion.size.medium",
      percent: Math.round((Math.sqrt(222 * 576) / 576) * 100),
    });
    expect(readoutFor(1, null, DESKTOP_RANGE)).toEqual({ labelKey: null, percent: 100 });
  });
});

describe("fitted figure (derived, never persisted)", () => {
  const keyboard: LayoutContext = {
    ...phone,
    visible: { top: 0, bottom: 500 },
    composer: { left: 0, top: 400, width: 390, height: 100 },
  };

  test("keyboard 844 → 500 → 844: the chosen level maps back to the exact size", () => {
    const level = 1;
    const open = figureForLevel(level, sizeRange("phone", phone));
    const shrunk = figureForLevel(level, sizeRange("phone", keyboard));
    const closed = figureForLevel(level, sizeRange("phone", phone));
    expect(shrunk.height).toBeLessThanOrEqual(open.height);
    expect(shrunk.height).toBeGreaterThanOrEqual(READABLE_FIGURE.height);
    expect(closed).toEqual(open);
  });

  test("with the keyboard open the figure uses the band up to just under the top", () => {
    const range = sizeRange("phone", keyboard);
    // feet line 394, top limit 8, 20px headroom: up to 366px tall, capped by width.
    expect(range.maxHeight).toBe(292);
    expect(fittedFigure(figureForLevel(1, range), "phone", keyboard).room).toBe(true);
  });

  test("desktop: shrinks to the free gutter, never below a readable size", () => {
    const roomy: LayoutContext = { ...desktop, column: { left: 305, top: 80, width: 700, height: 600 } };
    const chosen = figureForLevel(1, sizeRange("desktop", roomy));
    const fitted = fittedFigure(chosen, "desktop", roomy);
    expect(fitted.room).toBe(true);
    expect(fitted.figure.width).toBeLessThan(chosen.width);
    expect(fitted.figure.width).toBeGreaterThanOrEqual(READABLE_FIGURE.width);
  });

  test("desktop with no gutter at all: tuck away as a bookmark", () => {
    const chosen = figureForLevel(0.5, sizeRange("desktop", desktop));
    expect(fittedFigure(chosen, "desktop", desktop).room).toBe(false);
  });
});
