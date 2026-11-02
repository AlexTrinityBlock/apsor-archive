import { useEffect, useState } from "react";

/**
 * Observe an element's content width for fit-to-width document pages.
 *
 * Returns a callback ref and the observed width. A callback ref is required
 * because the measured element often mounts only after the viewer data has
 * loaded; an effect bound to a stable ref object would run once while the
 * element is still null and never observe it.
 */
export function useElementWidth<T extends HTMLElement>(): [
  (element: T | null) => void,
  number,
] {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!element) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setWidth(entry.contentRect.width);
      }
    });
    // ResizeObserver reports the current size when observation starts, so the
    // initial measurement does not need a synchronous setState in this effect.
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [setElement, width];
}
