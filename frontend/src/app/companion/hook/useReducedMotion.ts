import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(listener: () => void): () => void {
  const media = window.matchMedia?.(QUERY);
  if (!media) {
    return () => undefined;
  }
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

function getSnapshot(): boolean {
  return window.matchMedia?.(QUERY).matches ?? false;
}

/** The operating system's reduced-motion request, kept live. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
