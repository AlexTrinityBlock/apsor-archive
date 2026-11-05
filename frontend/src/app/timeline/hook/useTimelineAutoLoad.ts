/** Automatic earlier-window loading for the timeline spine. */

import { useEffect, useRef } from "react";

export interface UseTimelineAutoLoadOptions {
  readonly sentinel: HTMLElement | null;
  readonly enabled: boolean;
  readonly resetKey: string;
  readonly onLoad: () => void;
}

const LOAD_GUARD_MS = 250;
const MAX_AUTO_LOADS = 3;
const PRELOAD_DISTANCE_PX = 600;
const ROOT_MARGIN = "600px 0px";

function isNearSentinel(sentinel: HTMLElement): boolean {
  const rect = sentinel.getBoundingClientRect();
  return rect.top <= window.innerHeight + PRELOAD_DISTANCE_PX;
}

/**
 * Watches the spine sentinel and asks the page for the previous date window as
 * it approaches the viewport. A duplicate-load guard and a three-load ceiling
 * keep quiet archives from spinning through years of empty windows; a real
 * scroll clears the ceiling. Listeners attach to both the window and the
 * closest `.app-page` scroll owner so either shell layout works.
 */
export function useTimelineAutoLoad({
  sentinel,
  enabled,
  resetKey,
  onLoad,
}: UseTimelineAutoLoadOptions): void {
  const onLoadRef = useRef(onLoad);
  const enabledRef = useRef(enabled);
  const attemptRef = useRef<(() => void) | null>(null);
  const resetKeyRef = useRef(resetKey);
  const lastLoadAtRef = useRef(0);
  const autoLoadCountRef = useRef(0);

  useEffect(() => {
    onLoadRef.current = onLoad;
  }, [onLoad]);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  useEffect(() => {
    if (!sentinel) {
      attemptRef.current = null;
      return;
    }

    const scrollOwner = sentinel.closest(".app-page");
    const attempt = () => {
      if (!enabledRef.current || !isNearSentinel(sentinel)) {
        return;
      }
      if (autoLoadCountRef.current >= MAX_AUTO_LOADS) {
        return;
      }
      const now = Date.now();
      if (now - lastLoadAtRef.current < LOAD_GUARD_MS) {
        return;
      }
      lastLoadAtRef.current = now;
      autoLoadCountRef.current += 1;
      onLoadRef.current();
    };
    const handleScroll = () => {
      autoLoadCountRef.current = 0;
      attempt();
    };

    attemptRef.current = attempt;
    window.addEventListener("scroll", handleScroll, { passive: true });
    scrollOwner?.addEventListener("scroll", handleScroll, { passive: true });

    let observer: IntersectionObserver | null = null;
    if (typeof IntersectionObserver === "function") {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            attempt();
          }
        },
        { root: null, rootMargin: ROOT_MARGIN, threshold: 0 },
      );
      observer.observe(sentinel);
    }

    attempt();

    return () => {
      attemptRef.current = null;
      observer?.disconnect();
      window.removeEventListener("scroll", handleScroll);
      scrollOwner?.removeEventListener("scroll", handleScroll);
    };
  }, [sentinel]);

  useEffect(() => {
    if (resetKeyRef.current === resetKey) {
      return;
    }
    resetKeyRef.current = resetKey;
    autoLoadCountRef.current = 0;
    attemptRef.current?.();
  }, [resetKey]);

  useEffect(() => {
    if (enabled) {
      attemptRef.current?.();
    }
  }, [enabled]);
}
