import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

const STORAGE_KEY = "dendro_chat_inspector";
const DEFAULT_RATIO = 0.42;
const MIN_WIDTH = 280;
const STREAM_MIN_WIDTH = 320;
const MIN_RATIO = 0.2;
const MAX_RATIO = 0.85;
const DRAG_THRESHOLD = 4;

interface StoredSplit {
  readonly ratio: number;
  readonly collapsed: boolean;
}

function readStoredSplit(): StoredSplit {
  if (typeof window === "undefined") {
    return { ratio: DEFAULT_RATIO, collapsed: false };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ratio: DEFAULT_RATIO, collapsed: false };
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return { ratio: DEFAULT_RATIO, collapsed: false };
    }
    const record = parsed as Record<string, unknown>;
    const ratio =
      typeof record.ratio === "number" &&
      Number.isFinite(record.ratio) &&
      record.ratio >= MIN_RATIO &&
      record.ratio <= MAX_RATIO
        ? record.ratio
        : DEFAULT_RATIO;
    return { ratio, collapsed: record.collapsed === true };
  } catch {
    return { ratio: DEFAULT_RATIO, collapsed: false };
  }
}

function clampWidth(width: number, containerWidth: number): number {
  const max = Math.max(MIN_WIDTH, containerWidth - STREAM_MIN_WIDTH);
  return Math.min(max, Math.max(MIN_WIDTH, width));
}

/**
 * The horizontal stream/inspector split.
 *
 * The inspector stores a ratio of the workspace width. Drag uses pointer
 * capture; a pointer-up without movement collapses the inspector; the
 * separator supports arrow keys, Home/End, and Enter/Space.
 */
export function useChatSplit() {
  const [stored] = useState(readStoredSplit);
  const containerRef = useRef<HTMLDivElement>(null);
  const inspectorRef = useRef<HTMLElement>(null);
  const dragRef = useRef<{
    readonly startX: number;
    readonly startWidth: number;
    readonly wasCollapsed: boolean;
    moved: boolean;
  } | null>(null);

  const [ratio, setRatio] = useState(stored.ratio);
  const [collapsed, setCollapsed] = useState(stored.collapsed);
  const [dragging, setDragging] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    if (typeof ResizeObserver === "undefined") {
      setContainerWidth(container.clientWidth);
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    observer.observe(container);
    setContainerWidth(container.clientWidth);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ ratio, collapsed }),
      );
    } catch {
      // Storage can be unavailable in private contexts; the split still works.
    }
  }, [ratio, collapsed]);

  useEffect(() => {
    return () => {
      document.body.style.removeProperty("user-select");
    };
  }, []);

  const maxWidth =
    containerWidth > 0
      ? Math.max(MIN_WIDTH, containerWidth - STREAM_MIN_WIDTH)
      : MIN_WIDTH;
  const currentWidth = collapsed ? 0 : clampWidth(ratio * containerWidth, containerWidth);

  const open = useCallback(() => setCollapsed(false), []);

  const applyWidth = useCallback(
    (width: number) => {
      const container = containerRef.current;
      const widthOfContainer = container?.clientWidth ?? containerWidth;
      if (widthOfContainer <= 0) {
        return;
      }
      const next = clampWidth(width, widthOfContainer);
      setRatio(next / widthOfContainer);
    },
    [containerWidth],
  );

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) {
      return;
    }
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    dragRef.current = {
      startX: event.clientX,
      startWidth:
        inspectorRef.current?.getBoundingClientRect().width ?? currentWidth,
      wasCollapsed: collapsed,
      moved: false,
    };
    document.body.style.userSelect = "none";
    setDragging(true);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) {
      return;
    }
    if (Math.abs(event.clientX - drag.startX) > DRAG_THRESHOLD) {
      drag.moved = true;
    }
    if (drag.wasCollapsed) {
      return;
    }
    applyWidth(drag.startWidth + (drag.startX - event.clientX));
  };

  const finishPointer = (
    event: PointerEvent<HTMLDivElement>,
    cancelled: boolean,
  ) => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDragging(false);
    document.body.style.removeProperty("user-select");
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (!drag) {
      return;
    }
    if (drag.wasCollapsed) {
      setCollapsed(false);
      return;
    }
    if (!cancelled && !drag.moved) {
      setCollapsed(true);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 96 : 24;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setCollapsed((value) => !value);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setCollapsed(false);
      applyWidth(MIN_WIDTH);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setCollapsed(false);
      applyWidth(maxWidth);
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? step : -step;
      const base = collapsed
        ? MIN_WIDTH
        : (inspectorRef.current?.getBoundingClientRect().width ?? currentWidth);
      setCollapsed(false);
      applyWidth(base + delta);
    }
  };

  return {
    containerRef,
    inspectorRef,
    ratio,
    collapsed,
    dragging,
    containerWidth,
    maxWidth,
    currentWidth,
    open,
    toggle: () => setCollapsed((value) => !value),
    setCollapsed,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp: (event: PointerEvent<HTMLDivElement>) =>
      finishPointer(event, false),
    handlePointerCancel: (event: PointerEvent<HTMLDivElement>) =>
      finishPointer(event, true),
    handleKeyDown,
  };
}
