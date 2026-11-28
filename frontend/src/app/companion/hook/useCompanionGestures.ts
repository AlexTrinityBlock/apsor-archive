import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

import type { DragMotion } from "../component/CompanionStage";
import {
  IDLE,
  WHEEL_IDLE_MS,
  isActive,
  reduceGesture,
  type DragRelease,
  type GestureEffect,
  type GestureEvent,
  type GestureState,
  type HitTarget,
  type PointerKind,
  type ResizeSource,
} from "../gesture";


export interface GestureCallbacks {
  readonly onMoveStart: () => void;
  readonly onMove: (dx: number, dy: number) => void;
  readonly onMoveEnd: (release: DragRelease) => void;
  readonly onMoveAbort: () => void;
  readonly onResizeStart: (source: ResizeSource) => void;
  readonly onResizeGrip: (dx: number, dy: number) => void;
  readonly onResizePinch: (ratio: number) => void;
  readonly onResizeWheel: (deltaY: number, deltaMode: number) => void;
  readonly onResizeEnd: () => void;
  readonly onResizeCancel: () => void;
  readonly onTap: () => void;
  readonly onDoubleTap: () => void;
}

function pointerKind(value: string): PointerKind {
  return value === "touch" || value === "pen" ? value : "mouse";
}

function hitTarget(target: EventTarget | null): HitTarget {
  if (!(target instanceof Element)) {
    return "body";
  }
  if (target.closest("[data-companion-grip]") !== null) {
    return "grip";
  }
  return target.closest("button") !== null ? "control" : "body";
}

/**
 * Wires pointer and Ctrl/⌘+wheel events on the companion root into the pure
 * gesture machine. Live drag velocity is shared through `dragMotion` so the
 * stage can sway without React renders.
 */
export function useCompanionGestures(
  rootRef: RefObject<HTMLElement | null>,
  callbacks: GestureCallbacks,
) {
  const dragMotion = useRef<DragMotion>({ vx: 0 });
  const state = useRef<GestureState>(IDLE);
  const callbacksRef = useRef(callbacks);
  const wheelTimer = useRef<number | null>(null);
  useLayoutEffect(() => {
    callbacksRef.current = callbacks;
  });

  const run = useCallback((effects: readonly GestureEffect[], element: HTMLElement | null, id?: number) => {
    const handlers = callbacksRef.current;
    for (const effect of effects) {
      switch (effect.type) {
        case "capture":
          if (element !== null && id !== undefined && !element.hasPointerCapture(id)) {
            element.setPointerCapture(id);
          }
          break;
        case "moveStart":
          handlers.onMoveStart();
          break;
        case "move":
          dragMotion.current = { vx: effect.vx };
          handlers.onMove(effect.dx, effect.dy);
          break;
        case "moveEnd":
          dragMotion.current = { vx: 0 };
          handlers.onMoveEnd(effect.release);
          break;
        case "moveAbort":
          dragMotion.current = { vx: 0 };
          handlers.onMoveAbort();
          break;
        case "resizeStart":
          document.documentElement.classList.add("companion-resizing");
          handlers.onResizeStart(effect.source);
          break;
        case "resizeGrip":
          handlers.onResizeGrip(effect.dx, effect.dy);
          break;
        case "resizePinch":
          handlers.onResizePinch(effect.ratio);
          break;
        case "resizeWheel":
          handlers.onResizeWheel(effect.deltaY, effect.deltaMode);
          break;
        case "resizeEnd":
          document.documentElement.classList.remove("companion-resizing");
          handlers.onResizeEnd();
          break;
        case "resizeCancel":
          document.documentElement.classList.remove("companion-resizing");
          handlers.onResizeCancel();
          break;
        case "tap":
          handlers.onTap();
          break;
        case "doubleTap":
          handlers.onDoubleTap();
          break;
      }
    }
  }, []);

  const dispatch = useCallback(
    (event: GestureEvent, element: HTMLElement | null = null, id?: number) => {
      const next = reduceGesture(state.current, event);
      state.current = next.state;
      run(next.effects, element, id);
    },
    [run],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      dispatch(
        {
          type: "down",
          id: event.pointerId,
          pointer: pointerKind(event.pointerType),
          button: event.button,
          target: hitTarget(event.target),
          x: event.clientX,
          y: event.clientY,
          t: event.timeStamp,
        },
        event.currentTarget,
        event.pointerId,
      );
    },
    [dispatch],
  );

  const pointerEvent = useCallback(
    (type: "move" | "up" | "cancel") => (event: ReactPointerEvent<HTMLElement>) => {
      if (!isActive(state.current)) {
        return;
      }
      if (type === "move" && state.current.kind !== "pressed") {
        event.preventDefault();
      }
      dispatch({
        type,
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        t: event.timeStamp,
      });
      if (type !== "move" && event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [dispatch],
  );

  // Ctrl/⌘+wheel (and macOS trackpad pinch) over the figure resizes it; a
  // plain wheel scrolls the page as usual.
  useEffect(() => {
    const element = rootRef.current;
    if (element === null) {
      return undefined;
    }
    const onWheel = (event: WheelEvent) => {
      const modified = event.ctrlKey || event.metaKey;
      if (!modified) {
        return;
      }
      event.preventDefault();
      dispatch({
        type: "wheel",
        deltaY: event.deltaY,
        deltaMode: event.deltaMode,
        modified,
        t: event.timeStamp,
      });
      if (wheelTimer.current !== null) {
        window.clearTimeout(wheelTimer.current);
      }
      wheelTimer.current = window.setTimeout(() => {
        wheelTimer.current = null;
        dispatch({ type: "wheelIdle", t: performance.now() + WHEEL_IDLE_MS });
      }, WHEEL_IDLE_MS);
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      element.removeEventListener("wheel", onWheel);
      if (wheelTimer.current !== null) {
        window.clearTimeout(wheelTimer.current);
      }
      document.documentElement.classList.remove("companion-resizing");
    };
  }, [rootRef, dispatch]);

  /** Escape during a gesture cancels it; returns whether it was consumed. */
  const cancel = useCallback((): boolean => {
    if (!isActive(state.current) || state.current.kind === "pressed") {
      return false;
    }
    dispatch({ type: "escape" });
    return true;
  }, [dispatch]);

  return {
    onPointerDown,
    onPointerMove: pointerEvent("move"),
    onPointerUp: pointerEvent("up"),
    onPointerCancel: pointerEvent("cancel"),
    onLostPointerCapture: pointerEvent("cancel"),
    dragMotion,
    cancel,
  };
}
