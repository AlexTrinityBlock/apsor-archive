/**
 * Pure scroll-follow rules for the chat transcript. The hook in
 * `hook/useStickToBottom.ts` wires these to DOM events.
 */

/** Distance from the bottom that still counts as "reading the latest". */
export const STICK_THRESHOLD_PX = 24;

export interface ScrollMetrics {
  readonly scrollHeight: number;
  readonly scrollTop: number;
  readonly clientHeight: number;
}

/** Pixels between the visible bottom edge and the end of the content. */
export function distanceFromBottom(metrics: ScrollMetrics): number {
  return Math.max(
    0,
    metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight,
  );
}

/** Whether a scroll position should re-attach the reader to the live tail. */
export function isNearBottom(
  metrics: ScrollMetrics,
  threshold: number = STICK_THRESHOLD_PX,
): boolean {
  return distanceFromBottom(metrics) <= threshold;
}

const UNSTICK_KEYS: ReadonlySet<string> = new Set(["PageUp", "ArrowUp", "Home"]);

/** Keys that express "I want to read further up" on the scroll owner. */
export function isUnstickKey(key: string): boolean {
  return UNSTICK_KEYS.has(key);
}

/** An upward wheel gesture always detaches the reader from the tail. */
export function isUpwardWheel(deltaY: number): boolean {
  return deltaY < 0;
}

/**
 * Keep the same content under the reader after older rows are prepended:
 * the distance from the bottom is preserved, not the raw `scrollTop`.
 */
export function anchoredScrollTop(
  before: Pick<ScrollMetrics, "scrollHeight" | "scrollTop">,
  afterScrollHeight: number,
): number {
  const fromBottom = before.scrollHeight - before.scrollTop;
  return Math.max(0, afterScrollHeight - fromBottom);
}
