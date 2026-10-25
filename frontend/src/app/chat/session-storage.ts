/**
 * Remembers only the last conversation id so `/chat` can resume it.
 *
 * Nothing from the transcript is persisted here: no entries, drafts, tokens,
 * provider keys, or titles. Storage failures (private mode, disabled storage)
 * are deliberately silent so chat keeps working without the resume shortcut.
 */
const LAST_CHAT_KEY = "apsor-archive.chat.lastConversationId";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function isConversationId(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

/** Reads the saved conversation id, removing any malformed value. */
export function readLastChatConversation(): number | null {
  const store = storage();
  if (store === null) {
    return null;
  }
  try {
    const raw = store.getItem(LAST_CHAT_KEY);
    if (raw === null) {
      return null;
    }
    if (!/^\d+$/.test(raw)) {
      store.removeItem(LAST_CHAT_KEY);
      return null;
    }
    const parsed = Number.parseInt(raw, 10);
    if (!isConversationId(parsed)) {
      store.removeItem(LAST_CHAT_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** Saves a valid conversation id; invalid ids are ignored. */
export function rememberLastChatConversation(id: number): void {
  const store = storage();
  if (store === null || !isConversationId(id)) {
    return;
  }
  try {
    store.setItem(LAST_CHAT_KEY, String(id));
  } catch {
    // Storage can be unavailable; chat remains usable without the shortcut.
  }
}

/** Clears the saved conversation id, for example before an explicit new chat. */
export function clearLastChatConversation(): void {
  const store = storage();
  if (store === null) {
    return;
  }
  try {
    store.removeItem(LAST_CHAT_KEY);
  } catch {
    // Storage can be unavailable; chat remains usable without the shortcut.
  }
}
