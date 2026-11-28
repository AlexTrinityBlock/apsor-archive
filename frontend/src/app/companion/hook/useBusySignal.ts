import { useEffect, useState } from "react";

/** How long typing or scrolling keeps the companion faded in auto mode. */
const BUSY_MS = 1400;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLInputElement && target.type !== "checkbox" && target.type !== "radio") ||
    target.isContentEditable
  );
}

/**
 * True briefly after the reader types in a text field or scrolls anything on
 * the page. Auto opacity uses it to step out of the way while the reader is
 * busy. Listening is off unless `enabled`, so other modes pay nothing.
 */
export function useBusySignal(enabled: boolean): boolean {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    let timer = 0;
    const mark = () => {
      setBusy(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setBusy(false), BUSY_MS);
    };
    const onInput = (event: Event) => {
      if (isTypingTarget(event.target)) {
        mark();
      }
    };
    document.addEventListener("input", onInput, true);
    document.addEventListener("scroll", mark, { capture: true, passive: true });
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("scroll", mark, { capture: true });
      setBusy(false);
    };
  }, [enabled]);
  return enabled && busy;
}
