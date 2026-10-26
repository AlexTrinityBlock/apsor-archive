/**
 * Cross-tab session transition bus.
 *
 * Auth transitions replace a shared cookie, so other tabs hold a stale account,
 * dialog stack, draft, and React Query cache. They deliberately receive a full
 * reload instead of trying to reconcile partial UI state. BroadcastChannel is
 * the primary transport; localStorage's `storage` event is the fallback for
 * browsers without it.
 */
const CHANNEL_NAME = "apsor-archive:session-transition";
const STORAGE_KEY = "apsor-archive.session.transition";
const TAB_ID = createTabId();

interface SessionTransitionMessage {
  readonly source: string;
}

function createTabId(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    try {
      const bytes = crypto.getRandomValues(new Uint32Array(2));
      return `${bytes[0].toString(36)}-${bytes[1].toString(36)}`;
    } catch {
      // Fall through to the non-secret timestamp fallback.
    }
  }
  return Date.now().toString(36);
}

function isTransitionMessage(value: unknown): value is SessionTransitionMessage {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const source = (value as { source?: unknown }).source;
  return typeof source === "string" && source.length > 0;
}

function parseStoredMessage(value: string): SessionTransitionMessage | null {
  try {
    const parsed: unknown = JSON.parse(value);
    return isTransitionMessage(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Tells every other tab that the shared session changed. The acting tab is not
 * notified, so it keeps its in-progress navigation and query cache.
 */
export function broadcastSessionTransition(): void {
  const message: SessionTransitionMessage = { source: TAB_ID };

  if (typeof BroadcastChannel !== "undefined") {
    try {
      const channel = new BroadcastChannel(CHANNEL_NAME);
      channel.postMessage(message);
      channel.close();
      return;
    } catch {
      // Fall through to the storage fallback.
    }
  }

  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(message));
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // A private browser may reject storage; the current tab still works.
  }
}

/** Subscribes to transitions from other tabs and returns an unsubscribe fn. */
export function subscribeToSessionTransitions(
  onTransition: () => void,
): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  let channel: BroadcastChannel | null = null;
  const handleMessage = (value: unknown) => {
    if (!isTransitionMessage(value) || value.source === TAB_ID) {
      return;
    }
    onTransition();
  };

  if (typeof BroadcastChannel !== "undefined") {
    try {
      channel = new BroadcastChannel(CHANNEL_NAME);
      channel.onmessage = (event: MessageEvent<unknown>) =>
        handleMessage(event.data);
    } catch {
      channel = null;
    }
  }

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY || event.newValue === null) {
      return;
    }
    const message = parseStoredMessage(event.newValue);
    if (message) {
      handleMessage(message);
    }
  };

  window.addEventListener("storage", handleStorage);

  return () => {
    channel?.close();
    window.removeEventListener("storage", handleStorage);
  };
}
