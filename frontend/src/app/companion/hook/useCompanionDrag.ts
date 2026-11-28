import { useCallback, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";

import type { DragMotion } from "../component/CompanionStage";

export interface DragRelease {
  readonly dx: number;
  readonly dy: number;
  /** Release velocity in px/ms. */
  readonly vx: number;
  readonly vy: number;
}

interface DragCallbacks {
  readonly onStart: () => void;
  readonly onMove: (dx: number, dy: number) => void;
  readonly onEnd: (release: DragRelease) => void;
  readonly onTap: () => void;
}

interface Sample {
  readonly x: number;
  readonly y: number;
  readonly t: number;
}

/** Movement below this many px is a tap, not a drag. */
const DRAG_THRESHOLD = 6;
const VELOCITY_WINDOW_MS = 90;

function velocity(samples: readonly Sample[]): { vx: number; vy: number } {
  const last = samples.at(-1);
  if (last === undefined) {
    return { vx: 0, vy: 0 };
  }
  const first =
    samples.find((sample) => last.t - sample.t <= VELOCITY_WINDOW_MS) ?? last;
  const dt = last.t - first.t;
  if (dt <= 0) {
    return { vx: 0, vy: 0 };
  }
  return { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
}

/**
 * Pointer-event drag for mouse, pen, and touch. Pointer capture keeps the
 * gesture even when the finger leaves the figure; the live velocity is shared
 * through the returned `dragMotion` ref so the stage can swing without React
 * renders.
 */
export function useCompanionDrag(callbacks: DragCallbacks) {
  const dragMotion = useRef<DragMotion>({ vx: 0 });
  const gesture = useRef<{
    id: number;
    startX: number;
    startY: number;
    dragging: boolean;
    samples: Sample[];
  } | null>(null);
  const callbacksRef = useRef(callbacks);
  useLayoutEffect(() => {
    callbacksRef.current = callbacks;
  });

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest("button")) {
      return;
    }
    gesture.current = {
      id: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      dragging: false,
      samples: [{ x: event.clientX, y: event.clientY, t: event.timeStamp }],
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const current = gesture.current;
      if (current === null || current.id !== event.pointerId) {
        return;
      }
      const dx = event.clientX - current.startX;
      const dy = event.clientY - current.startY;
      if (!current.dragging) {
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD) {
          return;
        }
        current.dragging = true;
        callbacksRef.current.onStart();
      }
      event.preventDefault();
      current.samples.push({ x: event.clientX, y: event.clientY, t: event.timeStamp });
      if (current.samples.length > 12) {
        current.samples.shift();
      }
      dragMotion.current = { vx: velocity(current.samples).vx };
      callbacksRef.current.onMove(dx, dy);
    },
    [],
  );

  const finish = useCallback(
    (event: ReactPointerEvent<HTMLElement>, cancelled: boolean) => {
      const current = gesture.current;
      if (current === null || current.id !== event.pointerId) {
        return;
      }
      gesture.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      dragMotion.current = { vx: 0 };
      if (!current.dragging) {
        if (!cancelled) {
          callbacksRef.current.onTap();
        }
        return;
      }
      const { vx, vy } = cancelled ? { vx: 0, vy: 0 } : velocity(current.samples);
      callbacksRef.current.onEnd({
        dx: event.clientX - current.startX,
        dy: event.clientY - current.startY,
        vx,
        vy,
      });
    },
    [],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => finish(event, false),
    [finish],
  );
  const onPointerCancel = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => finish(event, true),
    [finish],
  );

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, dragMotion };
}
