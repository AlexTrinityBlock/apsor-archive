/**
 * Session cache for Markdown thumbnail snippets.
 *
 * The full original stays in the HTTP cache, but scrolling between board and
 * list views should not re-fetch or re-parse the same note. A failed snippet is
 * remembered for the session so a broken original is not requested on every
 * render. Entries are keyed by the same versioned key as document thumbnails.
 */

export type MarkdownSnippetEntry =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "failed" };

const MAX_ENTRIES = 200;

// Map iteration order is insertion order. A hit re-inserts the entry at the
// end, which makes the first key the least recently used one.
const entries = new Map<string, MarkdownSnippetEntry>();

/** Read a cached snippet and mark it as recently used. */
export function getMarkdownSnippet(key: string): MarkdownSnippetEntry | undefined {
  const entry = entries.get(key);
  if (entry === undefined) {
    return undefined;
  }
  entries.delete(key);
  entries.set(key, entry);
  return entry;
}

/** Store one extracted snippet and evict the oldest entry. */
export function setMarkdownSnippet(key: string, text: string): void {
  entries.delete(key);
  entries.set(key, { kind: "text", text });
  evictOverflow();
}

/** Remember that this version could not be read for the rest of the session. */
export function setMarkdownSnippetFailed(key: string): void {
  entries.delete(key);
  entries.set(key, { kind: "failed" });
  evictOverflow();
}

/** Clear the module cache. Intended for tests and explicit cache resets. */
export function resetMarkdownSnippets(): void {
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
