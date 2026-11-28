// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  EDGE_MARGIN,
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
import { marionetteStrings } from "./strings";

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

  test("box includes the string span", () => {
    expect(boxSize("desktop").height).toBeGreaterThan(222);
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

describe("marionette strings", () => {
  const base = {
    width: 150,
    span: 46,
    figureHeight: 222,
    anchor: { x: 0.5, y: 0.02 },
    swayDegrees: 0,
    slack: 0,
    tangled: false,
    time: 0,
  };

  test("three strings start at the bar", () => {
    const strings = marionetteStrings(base);
    expect(strings.map((item) => item.key)).toEqual(["head", "left", "right"]);
    expect(strings[0]?.d.startsWith("M 75 12")).toBe(true);
    expect(strings[0]?.fade).toBe(false);
  });

  test("tangled strings cross over", () => {
    const straight = marionetteStrings(base);
    const tangled = marionetteStrings({ ...base, tangled: true });
    expect(tangled[1]?.d.split(" ")[1]).toBe(straight[2]?.d.split(" ")[1]);
  });
});
