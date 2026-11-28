/**
 * Pure pointer/wheel gesture machine for the companion: tap, double-tap,
 * move (drag/throw), corner-grip resize, two-finger pinch, and Ctrl/⌘+wheel.
 * It reports raw deltas only; `size.ts` turns them into sizes.
 */

export type PointerKind = "mouse" | "pen" | "touch";
/** What the pointer landed on: the figure body, the resize grip, or a button. */
export type HitTarget = "body" | "grip" | "control";

export interface Point {
  readonly x: number;
  readonly y: number;
}

export interface Sample extends Point {
  readonly t: number;
}

interface Tap extends Point {
  readonly t: number;
  readonly pointer: PointerKind;
}

export type GestureState =
  | { readonly kind: "idle"; readonly lastTap: Tap | null }
  | {
      readonly kind: "pressed";
      readonly id: number;
      readonly pointer: PointerKind;
      readonly start: Point;
      readonly samples: readonly Sample[];
      readonly lastTap: Tap | null;
    }
  | {
      readonly kind: "moving";
      readonly id: number;
      readonly start: Point;
      readonly samples: readonly Sample[];
    }
  | { readonly kind: "grip"; readonly id: number; readonly start: Point }
  | {
      readonly kind: "pinch";
      readonly ids: readonly [number, number];
      readonly points: Readonly<Record<number, Point>>;
      readonly startDistance: number;
    }
  /** One finger left after a pinch; it does nothing until it lifts. */
  | { readonly kind: "pinchTail"; readonly id: number }
  | { readonly kind: "wheel"; readonly lastAt: number };

export type GestureEvent =
  | {
      readonly type: "down";
      readonly id: number;
      readonly pointer: PointerKind;
      readonly button: number;
      readonly target: HitTarget;
      readonly x: number;
      readonly y: number;
      readonly t: number;
    }
  | {
      readonly type: "move" | "up" | "cancel";
      readonly id: number;
      readonly x: number;
      readonly y: number;
      readonly t: number;
    }
  | {
      readonly type: "wheel";
      readonly deltaY: number;
      readonly deltaMode: number;
      readonly modified: boolean;
      readonly t: number;
    }
  | { readonly type: "wheelIdle"; readonly t: number }
  | { readonly type: "escape" };

export interface DragRelease {
  readonly dx: number;
  readonly dy: number;
  /** Release velocity in px/ms. */
  readonly vx: number;
  readonly vy: number;
}

export type ResizeSource = "grip" | "pinch" | "wheel";

export type GestureEffect =
  | { readonly type: "capture" }
  | { readonly type: "moveStart" }
  | { readonly type: "move"; readonly dx: number; readonly dy: number; readonly vx: number }
  | { readonly type: "moveEnd"; readonly release: DragRelease }
  | { readonly type: "moveAbort" }
  | { readonly type: "resizeStart"; readonly source: ResizeSource }
  | { readonly type: "resizeGrip"; readonly dx: number; readonly dy: number }
  | { readonly type: "resizePinch"; readonly ratio: number }
  | { readonly type: "resizeWheel"; readonly deltaY: number; readonly deltaMode: number }
  | { readonly type: "resizeEnd" }
  | { readonly type: "resizeCancel" }
  | { readonly type: "tap" }
  | { readonly type: "doubleTap" };

export interface GestureResult {
  readonly state: GestureState;
  readonly effects: readonly GestureEffect[];
}

/** Movement below this many px is a tap, not a drag. */
export const DRAG_THRESHOLD = 6;
export const DOUBLE_TAP_MS = 300;
/** Wheel resizing ends after this long without another wheel event. */
export const WHEEL_IDLE_MS = 400;
const VELOCITY_WINDOW_MS = 90;
const MAX_SAMPLES = 12;

export const IDLE: GestureState = { kind: "idle", lastTap: null };

export function velocity(samples: readonly Sample[]): { vx: number; vy: number } {
  const last = samples.at(-1);
  if (last === undefined) {
    return { vx: 0, vy: 0 };
  }
  const first = samples.find((sample) => last.t - sample.t <= VELOCITY_WINDOW_MS) ?? last;
  const dt = last.t - first.t;
  if (dt <= 0) {
    return { vx: 0, vy: 0 };
  }
  return { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
}

function pushSample(samples: readonly Sample[], sample: Sample): readonly Sample[] {
  const next = [...samples, sample];
  return next.length > MAX_SAMPLES ? next.slice(next.length - MAX_SAMPLES) : next;
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function isDoubleTap(previous: Tap | null, current: Tap): boolean {
  if (previous === null || current.t - previous.t > DOUBLE_TAP_MS) {
    return false;
  }
  const slop = current.pointer === "touch" ? 24 : 16;
  return distance(previous, current) <= slop;
}

function result(state: GestureState, ...effects: GestureEffect[]): GestureResult {
  return { state, effects };
}

function startFromIdle(
  event: Extract<GestureEvent, { type: "down" }>,
  lastTap: Tap | null,
  prefix: readonly GestureEffect[] = [],
): GestureResult {
  if (event.button !== 0 || event.target === "control") {
    return { state: { kind: "idle", lastTap }, effects: prefix };
  }
  const point = { x: event.x, y: event.y };
  if (event.target === "grip") {
    return {
      state: { kind: "grip", id: event.id, start: point },
      effects: [...prefix, { type: "capture" }, { type: "resizeStart", source: "grip" }],
    };
  }
  return {
    state: {
      kind: "pressed",
      id: event.id,
      pointer: event.pointer,
      start: point,
      samples: [{ ...point, t: event.t }],
      lastTap,
    },
    effects: [...prefix, { type: "capture" }],
  };
}

function startPinch(
  first: { readonly id: number; readonly point: Point },
  event: Extract<GestureEvent, { type: "down" }>,
  aborted: boolean,
): GestureResult {
  const second = { x: event.x, y: event.y };
  const effects: GestureEffect[] = [];
  if (aborted) {
    effects.push({ type: "moveAbort" });
  }
  effects.push({ type: "capture" }, { type: "resizeStart", source: "pinch" });
  return {
    state: {
      kind: "pinch",
      ids: [first.id, event.id],
      points: { [first.id]: first.point, [event.id]: second },
      startDistance: Math.max(1, distance(first.point, second)),
    },
    effects,
  };
}

function canPinch(event: Extract<GestureEvent, { type: "down" }>): boolean {
  return event.pointer !== "mouse" && event.target !== "control";
}

type StateOf<K extends GestureState["kind"]> = Extract<GestureState, { kind: K }>;
type PointerEventOf = Extract<GestureEvent, { type: "move" | "up" | "cancel" }>;

function reduceIdle(state: StateOf<"idle">, event: GestureEvent): GestureResult {
  if (event.type === "down") {
    return startFromIdle(event, state.lastTap);
  }
  if (event.type === "wheel" && event.modified) {
    return result(
      { kind: "wheel", lastAt: event.t },
      { type: "resizeStart", source: "wheel" },
      { type: "resizeWheel", deltaY: event.deltaY, deltaMode: event.deltaMode },
    );
  }
  return result(state);
}

function reduceWheel(state: StateOf<"wheel">, event: GestureEvent): GestureResult {
  switch (event.type) {
    case "wheel":
      return event.modified
        ? result(
            { kind: "wheel", lastAt: event.t },
            { type: "resizeWheel", deltaY: event.deltaY, deltaMode: event.deltaMode },
          )
        : result(state);
    case "wheelIdle":
      return event.t - state.lastAt >= WHEEL_IDLE_MS
        ? result(IDLE, { type: "resizeEnd" })
        : result(state);
    case "escape":
      return result(IDLE, { type: "resizeCancel" });
    case "down":
      return startFromIdle(event, null, [{ type: "resizeEnd" }]);
    default:
      return result(state);
  }
}

function pressedPointer(state: StateOf<"pressed">, event: PointerEventOf): GestureResult {
  if (event.type === "cancel") {
    return result({ kind: "idle", lastTap: state.lastTap });
  }
  if (event.type === "move") {
    const dx = event.x - state.start.x;
    const dy = event.y - state.start.y;
    const samples = pushSample(state.samples, { x: event.x, y: event.y, t: event.t });
    if (Math.hypot(dx, dy) < DRAG_THRESHOLD) {
      return result({ ...state, samples });
    }
    return result(
      { kind: "moving", id: state.id, start: state.start, samples },
      { type: "moveStart" },
      { type: "move", dx, dy, vx: velocity(samples).vx },
    );
  }
  // up: a tap, or the second tap of a double-tap.
  const tap: Tap = { x: event.x, y: event.y, t: event.t, pointer: state.pointer };
  if (isDoubleTap(state.lastTap, tap)) {
    return result({ kind: "idle", lastTap: null }, { type: "doubleTap" });
  }
  return result({ kind: "idle", lastTap: tap }, { type: "tap" });
}

function reducePressed(state: StateOf<"pressed">, event: GestureEvent): GestureResult {
  switch (event.type) {
    case "down":
      return event.id !== state.id && canPinch(event)
        ? startPinch({ id: state.id, point: state.start }, event, false)
        : result(state);
    case "escape":
      return result({ kind: "idle", lastTap: state.lastTap });
    case "wheel":
    case "wheelIdle":
      return result(state);
    default:
      return event.id === state.id ? pressedPointer(state, event) : result(state);
  }
}

function reduceMoving(state: StateOf<"moving">, event: GestureEvent): GestureResult {
  switch (event.type) {
    case "down": {
      if (event.id === state.id || !canPinch(event)) {
        return result(state);
      }
      const last = state.samples.at(-1) ?? { ...state.start, t: 0 };
      return startPinch({ id: state.id, point: { x: last.x, y: last.y } }, event, true);
    }
    case "escape":
      return result(IDLE, { type: "moveAbort" });
    case "wheel":
    case "wheelIdle":
      return result(state);
    default: {
      if (event.id !== state.id) {
        return result(state);
      }
      const dx = event.x - state.start.x;
      const dy = event.y - state.start.y;
      if (event.type === "move") {
        const samples = pushSample(state.samples, { x: event.x, y: event.y, t: event.t });
        return result({ ...state, samples }, { type: "move", dx, dy, vx: velocity(samples).vx });
      }
      const { vx, vy } = event.type === "cancel" ? { vx: 0, vy: 0 } : velocity(state.samples);
      return result(IDLE, { type: "moveEnd", release: { dx, dy, vx, vy } });
    }
  }
}

function reduceGrip(state: StateOf<"grip">, event: GestureEvent): GestureResult {
  switch (event.type) {
    case "escape":
      return result(IDLE, { type: "resizeCancel" });
    case "down":
    case "wheel":
    case "wheelIdle":
      return result(state);
    default:
      if (event.id !== state.id) {
        return result(state);
      }
      if (event.type === "move") {
        return result(state, {
          type: "resizeGrip",
          dx: event.x - state.start.x,
          dy: event.y - state.start.y,
        });
      }
      return result(IDLE, event.type === "up" ? { type: "resizeEnd" } : { type: "resizeCancel" });
  }
}

function reducePinch(state: StateOf<"pinch">, event: GestureEvent): GestureResult {
  switch (event.type) {
    case "escape":
      return result(IDLE, { type: "resizeCancel" });
    case "down":
    case "wheel":
    case "wheelIdle":
      return result(state);
    default: {
      if (!state.ids.includes(event.id)) {
        return result(state);
      }
      if (event.type === "move") {
        const points = { ...state.points, [event.id]: { x: event.x, y: event.y } };
        const a = points[state.ids[0]];
        const b = points[state.ids[1]];
        const ratio = a !== undefined && b !== undefined ? distance(a, b) / state.startDistance : 1;
        return result({ ...state, points }, { type: "resizePinch", ratio });
      }
      const other = state.ids[0] === event.id ? state.ids[1] : state.ids[0];
      return result(
        { kind: "pinchTail", id: other },
        event.type === "up" ? { type: "resizeEnd" } : { type: "resizeCancel" },
      );
    }
  }
}

function reducePinchTail(state: StateOf<"pinchTail">, event: GestureEvent): GestureResult {
  if ((event.type === "up" || event.type === "cancel") && event.id === state.id) {
    return result(IDLE);
  }
  return result(state);
}

/** Advance the gesture machine by one event. */
export function reduceGesture(state: GestureState, event: GestureEvent): GestureResult {
  switch (state.kind) {
    case "idle":
      return reduceIdle(state, event);
    case "wheel":
      return reduceWheel(state, event);
    case "pressed":
      return reducePressed(state, event);
    case "moving":
      return reduceMoving(state, event);
    case "grip":
      return reduceGrip(state, event);
    case "pinch":
      return reducePinch(state, event);
    case "pinchTail":
      return reducePinchTail(state, event);
  }
}

/** True while a pointer or wheel gesture is in progress. */
export function isActive(state: GestureState): boolean {
  return state.kind !== "idle";
}
