// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  EDGE_MARGIN,
  FIGURE_HEADROOM,
  anchorFeet,
  gutterWidth,
  peekGeometry,
  positionAt,
  shiftPosition,
  avoidance,
  bookmarkTop,
  boxSize,
  feetLine,
  keyboardOpen,
  topLimit,
  visibleBand,
  breakpointFor,
  defaultPosition,
  dockX,
  landingPosition,
  readSavedPosition,
  resolveBox,
  type LayoutContext,
} from "./layout";
import { breathing, isSettled, stepSpring, swayForVelocity, SWAY_SPRING } from "./spring";

const desktop: LayoutContext = {
  viewport: { width: 1440, height: 900 },
  panel: { left: 230, top: 60, width: 800, height: 840 },
  composer: { left: 250, top: 760, width: 760, height: 120 },
  column: { left: 290, top: 100, width: 680, height: 640 },
};

describe("breakpoints and sizes", () => {
  test("breakpoints", () => {
    expect(breakpointFor(390)).toBe("phone");
    expect(breakpointFor(800)).toBe("tablet");
    expect(breakpointFor(1440)).toBe("desktop");
  });

  test("box adds only a small headroom above the free-standing figure", () => {
    expect(boxSize("desktop").height).toBe(222 + FIGURE_HEADROOM);
    expect(FIGURE_HEADROOM).toBeLessThan(30);
  });
});

describe("dock lines", () => {
  const width = boxSize("desktop").width;

  test("viewport and panel lines", () => {
    expect(dockX("viewport-left", desktop, width)).toBe(EDGE_MARGIN);
    expect(dockX("viewport-right", desktop, width)).toBe(1440 - width - EDGE_MARGIN);
    expect(dockX("panel-left", desktop, width)).toBe(230 + EDGE_MARGIN);
    expect(dockX("panel-right", desktop, width)).toBe(1030 - width - EDGE_MARGIN);
  });

  test("panel lines fall back to the viewport without a panel", () => {
    const bare = { ...desktop, panel: null };
    expect(dockX("panel-right", bare, width)).toBe(dockX("viewport-right", bare, width));
  });
});

describe("positions", () => {
  test("default sits above the composer on desktop and at the edge on phones", () => {
    const position = defaultPosition("desktop", desktop);
    expect(position.side).toBe("panel-right");
    const box = resolveBox(position, desktop, boxSize("desktop"));
    expect(box.top + box.height).toBeLessThanOrEqual(760);
    expect(defaultPosition("phone", { ...desktop, viewport: { width: 390, height: 800 } }).side).toBe(
      "viewport-right",
    );
  });

  test("resolveBox keeps the box out of the composer band", () => {
    const box = resolveBox({ side: "panel-right", y: 0.95 }, desktop, boxSize("desktop"));
    expect(box.top + box.height).toBeLessThanOrEqual(760 - 6);
  });

  test("a throw lands on the nearest dock line in its direction", () => {
    const size = boxSize("desktop");
    const landing = landingPosition(600, 300, { x: 1, y: 0 }, desktop, size);
    expect(landing.side).toBe("panel-right");
    const left = landingPosition(400, 300, { x: -4, y: 0 }, desktop, size);
    expect(left.side).toBe("viewport-left");
  });

  test("viewport dock lines stay inside the main content, clear of the nav rail", () => {
    const width = boxSize("desktop").width;
    const withRail: LayoutContext = {
      ...desktop,
      content: { left: 230, top: 0, width: 1210, height: 900 },
    };
    expect(dockX("viewport-left", withRail, width)).toBe(230 + EDGE_MARGIN);
    expect(dockX("viewport-right", withRail, width)).toBe(1440 - width - EDGE_MARGIN);
    const thrownLeft = landingPosition(300, 300, { x: -4, y: 0 }, withRail, boxSize("desktop"));
    expect(dockX(thrownLeft.side, withRail, width)).toBeGreaterThanOrEqual(230 + EDGE_MARGIN);
  });

  test("readSavedPosition validates stored JSON", () => {
    expect(readSavedPosition({ side: "viewport-left", y: 2 })).toEqual({
      side: "viewport-left",
      y: 1,
    });
    expect(readSavedPosition({ side: "floor", y: 0.2 })).toBeNull();
    expect(readSavedPosition("x")).toBeNull();
  });
});

describe("avoidance", () => {
  const size = boxSize("desktop");

  test("dialogs hide, phones stay visible, overlap shrinks or tucks away, gutters are clear", () => {
    const inColumn = { left: 500, top: 300, ...size };
    const inGutter = { left: 1290, top: 300, ...size };
    expect(avoidance(inGutter, desktop, true, "desktop")).toBe("hidden");
    expect(avoidance(inGutter, desktop, false, "phone")).toBe("clear");
    expect(avoidance(inColumn, desktop, false, "desktop", "panel-right")).toBe("peek");
    expect(avoidance(inColumn, desktop, false, "desktop", "viewport-right")).toBe("retract");
    expect(avoidance(inGutter, desktop, false, "desktop")).toBe("clear");
  });

  test("with the keyboard open nothing slides, shrinks or tucks away", () => {
    const keyboard: LayoutContext = { ...desktop, visible: { top: 0, bottom: 420 } };
    const inColumn = { left: 500, top: 100, ...size };
    expect(avoidance(inColumn, keyboard, false, "desktop", "viewport-right")).toBe("clear");
    expect(avoidance(inColumn, keyboard, false, "phone")).toBe("clear");
  });
});

describe("spring", () => {
  test("settles on the target", () => {
    let state = { value: 10, velocity: 0 };
    for (let i = 0; i < 240; i += 1) {
      state = stepSpring(state, 0, 1 / 60, SWAY_SPRING);
    }
    expect(isSettled(state, 0)).toBe(true);
  });

  test("sway and breathing stay bounded", () => {
    expect(swayForVelocity(100)).toBe(-16);
    expect(swayForVelocity(-100)).toBe(16);
    for (const t of [0, 1000, 5000, 12_345]) {
      const { bob, sway } = breathing(t);
      expect(Math.abs(bob)).toBeLessThanOrEqual(2.2);
      expect(Math.abs(sway)).toBeLessThanOrEqual(1.1);
    }
  });
});

describe("feet-anchored placement", () => {
  test("positions record the feet and resolve from them", () => {
    const size = boxSize("desktop");
    const position = positionAt("panel-right", 300, size, desktop);
    expect(position.feet).toBeCloseTo((300 + size.height) / 900, 6);
    const bigger = { width: 240, height: 380 };
    const box = resolveBox(position, desktop, bigger);
    expect(box.top + box.height).toBeCloseTo(300 + size.height, 0);
  });

  test("old top-based positions still resolve", () => {
    const old = readSavedPosition({ side: "panel-right", y: 0.3 });
    expect(old).toEqual({ side: "panel-right", y: 0.3 });
    const box = resolveBox(old ?? { side: "panel-right", y: 0 }, desktop, boxSize("desktop"));
    expect(box.top).toBeCloseTo(270, 0);
    expect(readSavedPosition({ side: "panel-right", y: 0.3, feet: 0.6 })?.feet).toBeCloseTo(0.6, 9);
  });

  test("a resize keeps the feet within 1 px", () => {
    const size = boxSize("desktop");
    const from = resolveBox({ side: "panel-right", y: 0.4 }, desktop, size);
    const next = { width: 200, height: 320 };
    const anchored = anchorFeet({ side: "panel-right", y: 0.4 }, desktop, from, next);
    const placed = resolveBox(anchored, desktop, next);
    expect(Math.abs(placed.top + placed.height - (from.top + from.height))).toBeLessThanOrEqual(1);
  });

  test("when the head would cross the top, the feet move down but stay above the composer", () => {
    const size = boxSize("desktop");
    const from = resolveBox({ side: "panel-right", y: 0.1 }, desktop, size);
    const next = { width: 384, height: 596 };
    const anchored = anchorFeet({ side: "panel-right", y: 0.1 }, desktop, from, next);
    const placed = resolveBox(anchored, desktop, next);
    expect(placed.top).toBeGreaterThanOrEqual(64);
    expect(placed.top + placed.height).toBeLessThanOrEqual(760 - 6);
  });

  test("shiftPosition moves both edges", () => {
    const moved = shiftPosition({ side: "panel-left", y: 0.2, feet: 0.5 }, 0.1);
    expect(moved.y).toBeCloseTo(0.3, 6);
    expect(moved.feet).toBeCloseTo(0.6, 6);
    expect(shiftPosition({ side: "panel-left", y: 0.2 }, -0.5)).toEqual({ side: "panel-left", y: 0 });
  });
});

describe("peek geometry", () => {
  test("small boxes keep the classic peek amounts", () => {
    const roomy: LayoutContext = { ...desktop, column: { left: 600, top: 100, width: 300, height: 600 } };
    expect(peekGeometry({ width: 148, height: 242 }, roomy)).toEqual({ scale: 0.6, slide: 0.58 });
  });

  test("a full-size figure in a narrow gutter shrinks and slides further", () => {
    const narrow: LayoutContext = {
      ...desktop,
      content: { left: 230, top: 0, width: 1050, height: 800 },
      column: { left: 305, top: 100, width: 900, height: 640 },
    };
    const gutter = gutterWidth(narrow);
    const peek = peekGeometry({ width: 384, height: 596 }, narrow);
    expect(gutter).toBeLessThan(80);
    // Never shrinks into an unreadable sliver.
    expect(peek.scale).toBeCloseTo(0.45, 9);
    expect(peek.slide).toBeCloseTo(0.82, 9);
  });
});

describe("keyboard and the visual viewport", () => {
  const phone: LayoutContext = {
    viewport: { width: 390, height: 844 },
    panel: { left: 0, top: 56, width: 390, height: 788 },
    composer: { left: 0, top: 740, width: 390, height: 100 },
    column: { left: 12, top: 60, width: 366, height: 660 },
    content: { left: 0, top: 0, width: 390, height: 844 },
  };
  const box = { width: 187, height: 300 };
  // The keyboard covers the bottom 344px; the composer rides above it.
  const keyboard: LayoutContext = {
    ...phone,
    visible: { top: 0, bottom: 500, left: 0, right: 390 },
    composer: { left: 0, top: 400, width: 390, height: 100 },
  };

  const insideVisible = (rect: { left: number; top: number; width: number; height: number }, context: LayoutContext) => {
    const band = visibleBand(context);
    return (
      rect.left >= band.left &&
      rect.top >= band.top &&
      rect.left + rect.width <= band.right &&
      rect.top + rect.height <= band.bottom
    );
  };

  test("detects the keyboard from the visible band", () => {
    expect(keyboardOpen(phone)).toBe(false);
    expect(keyboardOpen(keyboard)).toBe(true);
  });

  test("with the keyboard open the head may rise into the header band", () => {
    expect(topLimit(phone)).toBe(64);
    expect(topLimit(keyboard)).toBe(8);
    expect(feetLine(keyboard)).toBe(394);
  });

  test("docked on either side, the box stays inside the visual viewport", () => {
    for (const side of ["viewport-left", "viewport-right", "panel-left", "panel-right"] as const) {
      const position = defaultPosition("phone", phone, box);
      const rect = resolveBox({ ...position, side }, keyboard, box);
      expect(insideVisible(rect, keyboard)).toBe(true);
      expect(rect.top + rect.height).toBeLessThanOrEqual(keyboard.composer!.top);
    }
  });

  test("after a drag the landing stays inside the visual viewport", () => {
    const landed = landingPosition(500, 700, { x: 3, y: 2 }, keyboard, box);
    expect(insideVisible(resolveBox(landed, keyboard, box), keyboard)).toBe(true);
  });

  test("a pinch-zoomed visual viewport clamps horizontally too", () => {
    const zoomed: LayoutContext = { ...keyboard, visible: { top: 0, bottom: 500, left: 60, right: 330 } };
    for (const side of ["viewport-left", "viewport-right"] as const) {
      const rect = resolveBox({ side, y: 0.3 }, zoomed, { width: 120, height: 180 });
      expect(insideVisible(rect, zoomed)).toBe(true);
    }
  });

  test("closing the keyboard restores the exact box", () => {
    const position = defaultPosition("phone", phone, box);
    const before = resolveBox(position, phone, box);
    resolveBox(position, keyboard, box);
    expect(resolveBox(position, phone, box)).toEqual(before);
  });

  test("the bookmark tab stays fully inside the visible band", () => {
    const placement = bookmarkTop(900, 56, keyboard);
    expect(placement.top).toBeGreaterThanOrEqual(64);
    expect(placement.top + 56).toBeLessThanOrEqual(500);
    expect(placement.right).toBe(0);
  });
});
