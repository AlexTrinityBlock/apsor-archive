import { useEffect, useRef, useState, type RefObject } from "react";

/**
 * Observe whether an element has approached the viewport.
 *
 * The observer disconnects after the first hit: thumbnails are decorative and
 * stay rendered once shown, so scrolling back does not restart work. Without
 * an `IntersectionObserver` (older embedded browsers) the element is treated
 * as visible so previews still appear.
 */
export function useInView<T extends Element>(
  rootMargin = "200px 0px",
): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(
    () => typeof IntersectionObserver === "undefined",
  );

  useEffect(() => {
    if (inView) {
      return;
    }
    const element = ref.current;
    if (element === null) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [inView, rootMargin]);

  return [ref, inView];
}
