/**
 * A small FIFO scheduler for document thumbnail renders.
 *
 * PDF, DOCX, and PPTX rendering share one budget of two concurrent jobs so a
 * folder with many documents cannot start a burst of PDF.js workers or canvas
 * layouts. Running jobs are allowed to finish because their result is cached;
 * queued jobs can be withdrawn through their `AbortSignal`. New jobs wait
 * while the page is hidden and resume on the next `visibilitychange`, without
 * polling.
 */

type RenderTask<T> = (signal: AbortSignal) => Promise<T>;

interface QueueEntry {
  readonly task: RenderTask<unknown>;
  readonly signal: AbortSignal | undefined;
  readonly resolve: (value: unknown) => void;
  readonly reject: (reason: unknown) => void;
  detach: () => void;
}

const MAX_CONCURRENT = 2;

const queue: QueueEntry[] = [];
const neverAborted = new AbortController();
let active = 0;
let generation = 0;
let listenerAttached = false;

function isDocumentHidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function handleVisibilityChange(): void {
  if (!isDocumentHidden()) {
    pump();
  }
}

function ensureVisibilityListener(): void {
  if (listenerAttached || typeof document === "undefined") {
    return;
  }
  document.addEventListener("visibilitychange", handleVisibilityChange);
  listenerAttached = true;
}

function pump(): void {
  if (isDocumentHidden()) {
    return;
  }
  while (active < MAX_CONCURRENT && queue.length > 0) {
    const entry = queue.shift();
    if (entry === undefined) {
      return;
    }
    start(entry);
  }
}

function start(entry: QueueEntry): void {
  const startedIn = generation;
  active += 1;
  entry.detach();
  const settle = () => {
    if (startedIn !== generation) {
      return;
    }
    active -= 1;
    pump();
  };
  let result: Promise<unknown>;
  try {
    result = entry.task(entry.signal ?? neverAborted.signal);
  } catch (error) {
    active -= 1;
    entry.reject(error);
    pump();
    return;
  }
  void result.then(entry.resolve, entry.reject).finally(settle);
}

/**
 * Queue one render. The task receives the caller's signal, or a signal that
 * never aborts when none was supplied. A pre-aborted call never starts.
 */
export function schedule<T>(
  task: RenderTask<T>,
  signal?: AbortSignal,
): Promise<T> {
  if (signal?.aborted) {
    return Promise.reject(signal.reason);
  }

  ensureVisibilityListener();

  return new Promise<T>((resolve, reject) => {
    const entry: QueueEntry = {
      task,
      signal,
      resolve: (value) => resolve(value as T),
      reject,
      detach: () => undefined,
    };

    if (signal !== undefined) {
      const onAbort = () => {
        const index = queue.indexOf(entry);
        if (index < 0) {
          return;
        }
        queue.splice(index, 1);
        entry.detach();
        reject(signal.reason);
      };
      signal.addEventListener("abort", onAbort, { once: true });
      entry.detach = () => signal.removeEventListener("abort", onAbort);
    }

    queue.push(entry);
    pump();
  });
}

/** Number of renders waiting for a slot; running renders are not counted. */
export function pendingCount(): number {
  return queue.length;
}

/**
 * Clear queued work and counters. Intended for tests that start from a clean
 * scheduler; active tasks should be settled before calling it.
 */
export function resetQueue(): void {
  generation += 1;
  for (const entry of queue.splice(0)) {
    entry.detach();
    entry.reject(new Error("Render queue reset"));
  }
  active = 0;
  if (listenerAttached && typeof document !== "undefined") {
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    listenerAttached = false;
  }
}
