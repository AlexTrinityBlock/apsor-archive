import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

import {
  isNearBottom,
  isUnstickKey,
  isUpwardWheel,
} from "../scroll-follow";

export interface StickToBottom {
  /** Whether the transcript is following the live tail. */
  readonly stuck: boolean;
  /** New content arrived while the reader was scrolled away. */
  readonly hasNewActivity: boolean;
  /** Re-attach to the tail and jump there now. */
  readonly scrollToLatest: () => void;
  /** Re-attach to the tail; the next layout pass pins the scroll. */
  readonly stick: () => void;
  /** Detach from the tail, e.g. before a deep-link jump or a history load. */
  readonly unstick: () => void;
}

/**
 * Follows the bottom of a scroll owner while the reader is there.
 *
 * Pinning runs in a layout effect so a token never paints one frame below
 * the fold, and a `ResizeObserver` re-pins on late growth (images, PDF pages,
 * charts, opened disclosures, the composer). Any upward intent detaches
 * immediately; only returning to within a few pixels of the end re-attaches.
 */
export function useStickToBottom(
  scrollRef: RefObject<HTMLElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  version: unknown,
): StickToBottom {
  const stuckRef = useRef(true);
  const [stuck, setStuck] = useState(true);
  const [hasNewActivity, setHasNewActivity] = useState(false);

  const setStuckValue = useCallback((value: boolean) => {
    stuckRef.current = value;
    setStuck(value);
    if (value) {
      setHasNewActivity(false);
    }
  }, []);

  const pin = useCallback(() => {
    const scroll = scrollRef.current;
    if (scroll && stuckRef.current) {
      scroll.scrollTop = scroll.scrollHeight;
    }
  }, [scrollRef]);

  const stick = useCallback(() => {
    setStuckValue(true);
    pin();
  }, [pin, setStuckValue]);

  const unstick = useCallback(() => {
    setStuckValue(false);
  }, [setStuckValue]);

  const scrollToLatest = useCallback(() => {
    setStuckValue(true);
    pin();
  }, [pin, setStuckValue]);

  useLayoutEffect(() => {
    if (stuckRef.current) {
      pin();
    }
  }, [pin, version]);

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) {
      return;
    }
    const detach = () => {
      if (stuckRef.current) {
        setStuckValue(false);
      }
    };
    const handleWheel = (event: WheelEvent) => {
      if (isUpwardWheel(event.deltaY)) {
        detach();
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (isUnstickKey(event.key)) {
        detach();
      }
    };
    let lastTop = scroll.scrollTop;
    const handleScroll = () => {
      const near = isNearBottom(scroll);
      const movedUp = scroll.scrollTop < lastTop;
      lastTop = scroll.scrollTop;
      if (near) {
        if (!stuckRef.current) {
          setStuckValue(true);
        }
      } else if (movedUp) {
        // Scrollbar drags and other gestures without a wheel event.
        detach();
      }
    };
    scroll.addEventListener("wheel", handleWheel, { passive: true });
    scroll.addEventListener("touchmove", detach, { passive: true });
    scroll.addEventListener("keydown", handleKey);
    scroll.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scroll.removeEventListener("wheel", handleWheel);
      scroll.removeEventListener("touchmove", detach);
      scroll.removeEventListener("keydown", handleKey);
      scroll.removeEventListener("scroll", handleScroll);
    };
  }, [scrollRef, setStuckValue]);

  useEffect(() => {
    const scroll = scrollRef.current;
    const content = contentRef.current;
    if (!scroll || !content || typeof ResizeObserver === "undefined") {
      return;
    }
    let lastHeight = content.offsetHeight;
    const observer = new ResizeObserver(() => {
      const height = content.offsetHeight;
      const grew = height > lastHeight;
      lastHeight = height;
      if (stuckRef.current) {
        pin();
      } else if (grew) {
        setHasNewActivity(true);
      }
    });
    observer.observe(content);
    observer.observe(scroll);
    return () => observer.disconnect();
  }, [contentRef, pin, scrollRef]);

  return { stuck, hasNewActivity, scrollToLatest, stick, unstick };
}
