import { lazy } from "react";

const CHUNK_ERROR_PATTERN =
  /failed to fetch dynamically imported module|importing a module script failed|error loading dynamically imported module|chunkloaderror|loading chunk|unable to preload css/i;

/**
 * True when a lazily imported chunk vanished, which happens when a tab that
 * was open before a deployment asks for a chunk the new build no longer has.
 */
export function isChunkError(error: unknown): boolean {
  if (error instanceof Error) {
    return CHUNK_ERROR_PATTERN.test(`${error.name} ${error.message}`);
  }
  return typeof error === "string" && CHUNK_ERROR_PATTERN.test(error);
}

const RETRY_DELAY_MS = 350;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Import a module, retrying once after a short pause when the chunk failed to
 * load. A transient network hiccup recovers silently; a chunk that truly no
 * longer exists still rejects, so the nearest error boundary can offer a
 * reload into the new build.
 */
export async function importWithRetry<T>(factory: () => Promise<T>): Promise<T> {
  try {
    return await factory();
  } catch (error) {
    if (!isChunkError(error)) {
      throw error;
    }
    await wait(RETRY_DELAY_MS);
    return factory();
  }
}

/** `React.lazy` with one retry when the chunk fails to load. */
export const lazyRetry = ((factory) =>
  lazy(() => importWithRetry(factory))) as typeof lazy;

const RELOAD_GUARD_KEY = "apsor-archive.chunk-reload-at";
const RELOAD_GUARD_MS = 60_000;

/**
 * Reload once into the new build. Returns false when a reload already
 * happened in the last minute, so a genuinely missing chunk cannot loop.
 */
export function reloadForNewBuild(): boolean {
  try {
    const last = Number(window.sessionStorage.getItem(RELOAD_GUARD_KEY) ?? "0");
    if (Date.now() - last < RELOAD_GUARD_MS) {
      return false;
    }
    window.sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
  } catch {
    // Storage can be blocked; reload anyway, the user asked for it.
  }
  window.location.reload();
  return true;
}
