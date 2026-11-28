/**
 * In-memory composer drafts keyed by conversation. Drafts never touch
 * storage, matching the rule that transcript text stays out of the browser
 * store; the keyed page canvas drops them on an account switch.
 *
 * A plain record (not a `Map`) keeps the state immutable-by-convention, which
 * the React Compiler can memoize around.
 */

/** A conversation id, or `"new"` for the unsaved conversation at `/chat`. */
export type DraftKey = `${number}` | "new";

export type DraftMap = Readonly<Partial<Record<DraftKey, string>>>;

export const EMPTY_DRAFTS: DraftMap = {};

export function draftKey(conversationId: number | null): DraftKey {
  return conversationId === null ? "new" : `${conversationId}`;
}

export function readDraft(drafts: DraftMap, key: DraftKey): string {
  return drafts[key] ?? "";
}

/** Return a new record with `value` stored; an empty draft removes the key. */
export function writeDraft(
  drafts: DraftMap,
  key: DraftKey,
  value: string,
): DraftMap {
  if (readDraft(drafts, key) === value) {
    return drafts;
  }
  const next: Partial<Record<DraftKey, string>> = { ...drafts };
  if (value.length === 0) {
    delete next[key];
  } else {
    next[key] = value;
  }
  return next;
}
