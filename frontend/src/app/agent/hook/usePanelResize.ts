import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

const STORAGE_KEY = "dendromatrix.agentDock.panelHeight";
const MIN_PANEL_HEIGHT = 320;
const ABSOLUTE_MIN_HEIGHT = 240;
const TOP_GAP = 16;
const KEYBOARD_STEP = 24;
const KEYBOARD_FAST_STEP = 96;

export interface PanelResizeHandleProps {
  readonly onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  readonly onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
  readonly onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
  readonly onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
  readonly onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
}

interface PanelBounds {
  readonly min: number;
  readonly max: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStoredHeight(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
  } catch {
    // Private browsing can reject storage reads; the CSS default still works.
    return null;
  }
}

function storeHeight(height: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(Math.round(height)));
  } catch {
    // The chosen height still survives until the panel unmounts.
  }
}

/**
 * Resizes the docked agent panel from its top edge.
 *
 * The height lives in localStorage, is clamped against the panel's real bottom
 * anchor (safe area and mobile tabs included), and is ignored while the panel
 * is a full-height sheet. Pointer capture keeps the drag alive outside the
 * handle, and `resizing` lets the panel suppress text selection.
 */
export function usePanelResize(enabled: boolean, panelRef: RefObject<HTMLElement | null>) {
  const [height, setHeight] = useState<number | null>(readStoredHeight);
  const [measuredHeight, setMeasuredHeight] = useState<number | null>(null);
  const [minHeight, setMinHeight] = useState(MIN_PANEL_HEIGHT);
  const [maxHeight, setMaxHeight] = useState(MIN_PANEL_HEIGHT);
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef<{
    readonly pointerId: number;
    readonly startY: number;
    readonly startHeight: number;
  } | null>(null);

  const readBounds = useCallback((): PanelBounds => {
    const node = panelRef.current;
    const rect = node?.getBoundingClientRect();
    const max = Math.max(
      ABSOLUTE_MIN_HEIGHT,
      Math.floor((rect?.bottom ?? window.innerHeight) - TOP_GAP),
    );
    return { min: Math.min(MIN_PANEL_HEIGHT, max), max };
  }, [panelRef]);

  const resolvedHeight =
    height ?? measuredHeight ?? Math.max(maxHeight, MIN_PANEL_HEIGHT);

  useLayoutEffect(() => {
    if (!enabled) {
      return;
    }
    const update = () => {
      const node = panelRef.current;
      if (!node) {
        return;
      }
      const bounds = readBounds();
      setMinHeight(bounds.min);
      setMaxHeight(bounds.max);
      setMeasuredHeight(Math.round(node.getBoundingClientRect().height));
      setHeight((current) => {
        if (current === null) {
          return current;
        }
        const next = clamp(current, bounds.min, bounds.max);
        return next === current ? current : next;
      });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [enabled, panelRef, readBounds]);

  useEffect(() => {
    if (height === null) {
      return;
    }
    const timer = window.setTimeout(() => storeHeight(height), 160);
    return () => window.clearTimeout(timer);
  }, [height]);

  useEffect(() => {
    if (!resizing) {
      return;
    }
    document.body.classList.add("pi-agent-resizing");
    return () => {
      document.body.classList.remove("pi-agent-resizing");
    };
  }, [resizing]);

  useEffect(
    () => () => {
      dragRef.current = null;
      document.body.classList.remove("pi-agent-resizing");
    },
    [],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!enabled || event.button !== 0) {
        return;
      }
      const node = panelRef.current;
      if (!node) {
        return;
      }
      event.preventDefault();
      const bounds = readBounds();
      const rect = node.getBoundingClientRect();
      const startHeight = clamp(height ?? rect.height, bounds.min, bounds.max);
      setMinHeight(bounds.min);
      setMaxHeight(bounds.max);
      setHeight(startHeight);
      setResizing(true);
      dragRef.current = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.currentTarget.focus();
    },
    [enabled, height, panelRef, readBounds],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      const bounds = readBounds();
      setHeight(
        clamp(drag.startHeight + (drag.startY - event.clientY), bounds.min, bounds.max),
      );
    },
    [readBounds],
  );

  const endDrag = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    dragRef.current = null;
    setResizing(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      if (!enabled) {
        return;
      }
      const bounds = readBounds();
      const node = panelRef.current;
      const current = clamp(
        height ?? node?.getBoundingClientRect().height ?? bounds.max,
        bounds.min,
        bounds.max,
      );
      let next: number;
      switch (event.key) {
        case "ArrowUp":
          next = current + (event.shiftKey ? KEYBOARD_FAST_STEP : KEYBOARD_STEP);
          break;
        case "ArrowDown":
          next = current - (event.shiftKey ? KEYBOARD_FAST_STEP : KEYBOARD_STEP);
          break;
        case "Home":
          next = bounds.min;
          break;
        case "End":
          next = bounds.max;
          break;
        default:
          return;
      }
      event.preventDefault();
      setMinHeight(bounds.min);
      setMaxHeight(bounds.max);
      setHeight(clamp(next, bounds.min, bounds.max));
    },
    [enabled, height, panelRef, readBounds],
  );

  const handleProps: PanelResizeHandleProps = {
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onKeyDown,
  };

  return {
    height,
    resolvedHeight,
    maxHeight,
    minHeight,
    resizing,
    handleProps,
  };
}
