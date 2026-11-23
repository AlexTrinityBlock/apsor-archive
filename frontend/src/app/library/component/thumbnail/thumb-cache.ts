/**
 * Session cache for rendered document thumbnails.
 *
 * PDF and PPTX thumbnails are small WebP data URLs, so they can be shared by
 * the board and the list while the user browses a folder. Images are not
 * stored here: their HTTP response already lives in the browser cache. A
 * failure marker is kept for the session so a broken original is not fetched
 * again on every render or scroll.
 */

export type ThumbEntry = { kind: "image"; dataUrl: string } | { kind: "failed" };

const MAX_ENTRIES = 200;

// Map iteration order is insertion order. A hit re-inserts the entry at the
// end, which makes the first key the least recently used one.
const entries = new Map<string, ThumbEntry>();

/** Read a cached preview and mark it as recently used. */
export function getThumb(key: string): ThumbEntry | undefined {
  const entry = entries.get(key);
  if (entry === undefined) {
    return undefined;
  }
  entries.delete(key);
  entries.set(key, entry);
  return entry;
}

/** Store a rendered first page or slide and evict the oldest entry. */
export function setThumbImage(key: string, dataUrl: string): void {
  entries.delete(key);
  entries.set(key, { kind: "image", dataUrl });
  evictOverflow();
}

/** Remember that this version cannot be rendered for the rest of the session. */
export function setThumbFailed(key: string): void {
  entries.delete(key);
  entries.set(key, { kind: "failed" });
  evictOverflow();
}

/** Clear the module cache. Intended for tests and explicit cache resets. */
export function resetThumbs(): void {
  entries.clear();
}

function evictOverflow(): void {
  while (entries.size > MAX_ENTRIES) {
    const oldest = entries.keys().next();
    if (oldest.done) {
      return;
    }
    entries.delete(oldest.value);
  }
}
