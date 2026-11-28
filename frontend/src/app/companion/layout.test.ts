// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  EDGE_MARGIN,
  FIGURE_HEADROOM,
  INTRINSIC_FIGURE,
  boxSizeFor,
  figureSizeFor,
  gutterWidth,
  targetFigure,
  avoidance,
  boxSize,
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

  test("dialogs hide, phones peek, column overlap peeks, gutters are clear", () => {
    const inColumn = { left: 500, top: 300, ...size };
    const inGutter = { left: 1290, top: 300, ...size };
    expect(avoidance(inGutter, desktop, true, "desktop")).toBe("hidden");
    expect(avoidance(inGutter, desktop, false, "phone")).toBe("peek");
    expect(avoidance(inColumn, desktop, false, "desktop")).toBe("peek");
    expect(avoidance(inGutter, desktop, false, "desktop")).toBe("clear");
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

describe("size settings", () => {
  const roomy: LayoutContext = {
    viewport: { width: 2560, height: 1440 },
    panel: { left: 230, top: 60, width: 2330, height: 1380 },
    composer: { left: 900, top: 1300, width: 760, height: 120 },
    column: { left: 900, top: 100, width: 760, height: 1180 },
    content: { left: 230, top: 0, width: 2330, height: 1440 },
  };

  test("targets: compact is the old default, full is the intrinsic art", () => {
    expect(targetFigure("compact", "desktop")).toEqual({ width: 148, height: 222 });
    expect(targetFigure("full", "desktop")).toEqual(INTRINSIC_FIGURE);
    expect(targetFigure("medium", "desktop").height).toBeGreaterThan(222);
    expect(targetFigure("medium", "desktop").height).toBeLessThan(576);
  });

  test("full renders at intrinsic size when there is room, never larger", () => {
    expect(figureSizeFor("full", "desktop", roomy)).toEqual(INTRINSIC_FIGURE);
  });

  test("full scales down to fit the viewport height", () => {
    const short = { ...roomy, viewport: { width: 2560, height: 500 } };
    const figure = figureSizeFor("full", "desktop", short);
    expect(figure.height).toBeLessThanOrEqual(500 - FIGURE_HEADROOM);
    expect(figure.height).toBeLessThan(576);
    expect(figure.width).toBe(Math.round((figure.height * 2) / 3));
  });

  test("full scales down to fit the free gutter beside the column", () => {
    const gutter = gutterWidth(desktop);
    const figure = figureSizeFor("full", "desktop", desktop);
    expect(figure.width).toBeLessThanOrEqual(Math.max(gutter, 148) + 1);
  });

  test("never below compact; a too-narrow gutter is left to avoidance", () => {
    // The column fills the content area right of the 230 px nav rail.
    const narrow: LayoutContext = {
      ...desktop,
      content: { left: 230, top: 0, width: 1210, height: 900 },
      column: { left: 240, top: 100, width: 1190, height: 640 },
    };
    expect(figureSizeFor("full", "desktop", narrow)).toEqual({ width: 148, height: 222 });
  });

  test("box adds the headroom to the fitted figure", () => {
    const box = boxSizeFor("full", "desktop", roomy);
    expect(box).toEqual({ width: 384, height: 576 + FIGURE_HEADROOM });
  });

  test("a full figure in a roomy gutter does not cover the column or composer", () => {
    const box = boxSizeFor("full", "desktop", roomy);
    const placed = resolveBox(defaultPosition("desktop", roomy, box), roomy, box);
    expect(avoidance(placed, roomy, false, "desktop")).toBe("clear");
    expect(placed.top + placed.height).toBeLessThanOrEqual(roomy.composer?.top ?? 0);
  });
});
