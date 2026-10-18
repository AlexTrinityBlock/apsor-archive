import { useEffect } from "react";

/**
 * Prevents the page behind a modal or drawer from scrolling.
 *
 * @param locked - Whether scrolling should currently be disabled.
 */
export function useScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [locked]);
}
