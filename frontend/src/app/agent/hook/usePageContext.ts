/**
 * Watches `#main-content` and keeps one plain-text page snapshot current.
 *
 * The observer is debounced so async page loads settle into a single capture;
 * route changes always recapture immediately. `/chat` is skipped by the
 * capture utility because the full desk is the conversation itself.
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  capturePageContext,
  type PageContextSnapshot,
} from "../page-context";

const CAPTURE_DELAY_MS = 220;

/** The current page snapshot, or `null` on `/chat` and viewer routes. */
export function usePageContext(
  enabled = true,
): PageContextSnapshot | null {
  const location = useLocation();
  const [context, setContext] = useState<PageContextSnapshot | null>(null);

  useEffect(() => {
    if (!enabled) {
      const clear = window.setTimeout(() => setContext(null), 0);
      return () => window.clearTimeout(clear);
    }

    let timer: number | null = null;
    const capture = () => {
      timer = null;
      setContext(capturePageContext(location.pathname, location.search));
    };
    const schedule = () => {
      if (timer !== null) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(capture, CAPTURE_DELAY_MS);
    };

    let initial: number | null = window.setTimeout(capture, 0);

    const main = document.getElementById("main-content");
    if (!main) {
      return () => {
        if (initial !== null) {
          window.clearTimeout(initial);
          initial = null;
        }
        if (timer !== null) {
          window.clearTimeout(timer);
        }
      };
    }

    const observer = new MutationObserver(schedule);
    observer.observe(main, {
      subtree: true,
      childList: true,
      characterData: true,
    });

    return () => {
      observer.disconnect();
      if (initial !== null) {
        window.clearTimeout(initial);
        initial = null;
      }
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, [enabled, location.pathname, location.search]);

  return context;
}
