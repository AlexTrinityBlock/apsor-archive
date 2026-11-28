// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  IDLE,
  reduceGesture,
  type GestureEffect,
  type GestureEvent,
  type GestureState,
  type HitTarget,
  type PointerKind,
} from "./gesture";

function run(events: readonly GestureEvent[], start: GestureState = IDLE) {
  let state = start;
  const effects: GestureEffect[] = [];
  for (const event of events) {
    const next = reduceGesture(state, event);
    state = next.state;
    effects.push(...next.effects);
  }
  return { state, types: effects.map((effect) => effect.type), effects };
}

function down(
  id: number,
  x: number,
  y: number,
  t: number,
  target: HitTarget = "body",
  pointer: PointerKind = "mouse",
  button = 0,
): GestureEvent {
  return { type: "down", id, pointer, button, target, x, y, t };
}

const move = (id: number, x: number, y: number, t: number): GestureEvent => ({
  type: "move",
  id,
  x,
  y,
  t,
});
const up = (id: number, x: number, y: number, t: number): GestureEvent => ({
  type: "up",
  id,
  x,
  y,
  t,
});

describe("taps", () => {
  test("a press without movement is a tap", () => {
    expect(run([down(1, 10, 10, 0), up(1, 11, 10, 50)]).types).toEqual(["capture", "tap"]);
  });

  test("two taps within 300 ms and 16 px make a double-tap", () => {
    const result = run([
      down(1, 10, 10, 0),
      up(1, 10, 10, 40),
      down(2, 14, 12, 200),
      up(2, 14, 12, 240),
    ]);
    expect(result.types).toEqual(["capture", "tap", "capture", "doubleTap"]);
  });

  test("a slow second tap is just another tap", () => {
    const result = run([down(1, 10, 10, 0), up(1, 10, 10, 40), down(2, 10, 10, 400), up(2, 10, 10, 440)]);
    expect(result.types.filter((type) => type === "doubleTap")).toEqual([]);
  });

  test("touch allows a looser double-tap slop", () => {
    const result = run([
      down(1, 10, 10, 0, "body", "touch"),
      up(1, 10, 10, 30),
      down(2, 30, 20, 150, "body", "touch"),
      up(2, 30, 20, 180),
    ]);
    expect(result.types).toContain("doubleTap");
  });
});

describe("moving", () => {
  test("the 6 px threshold starts a move; release reports velocity", () => {
    const result = run([down(1, 0, 0, 0), move(1, 3, 0, 10), move(1, 20, 0, 20), up(1, 40, 0, 30)]);
    expect(result.types).toEqual(["capture", "moveStart", "move", "moveEnd"]);
    const end = result.effects.at(-1);
    expect(end?.type === "moveEnd" && end.release.dx).toBe(40);
  });

  test("escape aborts a move", () => {
    const result = run([down(1, 0, 0, 0), move(1, 20, 0, 10), { type: "escape" }]);
    expect(result.types.at(-1)).toBe("moveAbort");
    expect(result.state.kind).toBe("idle");
  });

  test("non-primary buttons and buttons inside the figure are ignored", () => {
    expect(run([down(1, 0, 0, 0, "body", "mouse", 2)]).types).toEqual([]);
    expect(run([down(1, 0, 0, 0, "control")]).types).toEqual([]);
  });

  test("unknown pointer ids are ignored", () => {
    const result = run([down(1, 0, 0, 0), move(9, 50, 0, 10), up(9, 50, 0, 20)]);
    expect(result.state.kind).toBe("pressed");
  });
});

describe("resizing", () => {
  test("grip drags resize at once and never tap", () => {
    const result = run([down(1, 0, 0, 0, "grip"), move(1, -2, -3, 10), up(1, -2, -3, 20)]);
    expect(result.types).toEqual(["capture", "resizeStart", "resizeGrip", "resizeEnd"]);
    expect(run([down(1, 0, 0, 0, "grip"), up(1, 0, 0, 20)]).types).not.toContain("tap");
  });

  test("escape cancels a grip resize", () => {
    const result = run([down(1, 0, 0, 0, "grip"), move(1, -20, -30, 10), { type: "escape" }]);
    expect(result.types.at(-1)).toBe("resizeCancel");
  });

  test("a second finger starts a pinch, aborting any move", () => {
    const result = run([
      down(1, 100, 100, 0, "body", "touch"),
      move(1, 120, 100, 10),
      down(2, 140, 100, 20, "body", "touch"),
      move(2, 180, 100, 30),
    ]);
    expect(result.types).toEqual([
      "capture",
      "moveStart",
      "move",
      "moveAbort",
      "capture",
      "resizeStart",
      "resizePinch",
    ]);
    const pinch = result.effects.at(-1);
    expect(pinch?.type === "resizePinch" && pinch.ratio).toBeCloseTo(3, 6);
  });

  test("lifting one finger ends the pinch; the other then does nothing", () => {
    const result = run([
      down(1, 100, 100, 0, "body", "touch"),
      down(2, 140, 100, 20, "body", "touch"),
      up(2, 140, 100, 40),
      move(1, 300, 100, 50),
      up(1, 300, 100, 60),
    ]);
    expect(result.types).toEqual(["capture", "capture", "resizeStart", "resizeEnd"]);
    expect(result.state.kind).toBe("idle");
  });

  test("a mouse never starts a pinch", () => {
    const result = run([down(1, 0, 0, 0), down(2, 50, 0, 10)]);
    expect(result.types).toEqual(["capture"]);
  });

  test("ctrl-wheel resizes until it goes quiet", () => {
    const result = run([
      { type: "wheel", deltaY: -100, deltaMode: 0, modified: true, t: 0 },
      { type: "wheel", deltaY: -100, deltaMode: 0, modified: true, t: 50 },
      { type: "wheelIdle", t: 200 },
      { type: "wheelIdle", t: 500 },
    ]);
    expect(result.types).toEqual(["resizeStart", "resizeWheel", "resizeWheel", "resizeEnd"]);
  });

  test("plain wheel and wheel during a pointer gesture are ignored", () => {
    expect(run([{ type: "wheel", deltaY: -100, deltaMode: 0, modified: false, t: 0 }]).types).toEqual([]);
    const during = run([
      down(1, 0, 0, 0, "grip"),
      { type: "wheel", deltaY: -100, deltaMode: 0, modified: true, t: 10 },
    ]);
    expect(during.types).toEqual(["capture", "resizeStart"]);
  });

  test("a press during a wheel resize ends it first", () => {
    const result = run([
      { type: "wheel", deltaY: -100, deltaMode: 0, modified: true, t: 0 },
      down(1, 0, 0, 50),
    ]);
    expect(result.types).toEqual(["resizeStart", "resizeWheel", "resizeEnd", "capture"]);
  });
});
