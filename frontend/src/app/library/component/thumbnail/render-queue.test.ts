// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { afterEach, expect, test } from "bun:test";

import { pendingCount, resetQueue, schedule } from "./render-queue";

interface Deferred<T> {
  readonly promise: Promise<T>;
  readonly resolve: (value: T) => void;
  readonly reject: (reason?: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

/** Let queued promise continuations run without a real timer. */
async function flush(): Promise<void> {
  for (let turn = 0; turn < 10; turn += 1) {
    await Promise.resolve();
  }
}

afterEach(() => {
  resetQueue();
});

test("at most two document renders run at once", async () => {
  const gates = [deferred<void>(), deferred<void>(), deferred<void>()];
  const started: number[] = [];
  let running = 0;
  let peak = 0;

  const tasks = gates.map((gate, index) =>
    schedule(async () => {
      started.push(index);
      running += 1;
      peak = Math.max(peak, running);
      await gate.promise;
      running -= 1;
      return index;
    }),
  );

  await flush();
  expect(started).toEqual([0, 1]);
  expect(pendingCount()).toBe(1);

  gates[0].resolve(undefined);
  await flush();
  expect(started).toEqual([0, 1, 2]);

  gates[1].resolve(undefined);
  gates[2].resolve(undefined);
  await Promise.all(tasks);
  expect(peak).toBe(2);
  expect(pendingCount()).toBe(0);
});

test("queued renders start in schedule order as slots free up", async () => {
  const gates = [deferred<void>(), deferred<void>(), deferred<void>(), deferred<void>()];
  const started: number[] = [];

  const tasks = [0, 1, 2, 3].map((index) =>
    schedule(async () => {
      started.push(index);
      await gates[index].promise;
      return index;
    }),
  );

  await flush();
  expect(started).toEqual([0, 1]);

  gates[0].resolve(undefined);
  await flush();
  expect(started).toEqual([0, 1, 2]);

  gates[1].resolve(undefined);
  await flush();
  expect(started).toEqual([0, 1, 2, 3]);

  gates[2].resolve(undefined);
  gates[3].resolve(undefined);
  await Promise.all(tasks);
  expect(pendingCount()).toBe(0);
});

test("a pre-aborted render never starts and rejects with the abort reason", async () => {
  const controller = new AbortController();
  controller.abort("stopped");
  let started = false;

  let reason: unknown;
  try {
    await schedule(async () => {
      started = true;
      return 1;
    }, controller.signal);
  } catch (error) {
    reason = error;
  }

  expect(reason).toBe("stopped");
  expect(started).toBe(false);
  expect(pendingCount()).toBe(0);
});

test("aborting a queued render removes it before it starts", async () => {
  const first = deferred<void>();
  const second = deferred<void>();
  const controller = new AbortController();
  let queuedStarted = false;

  const blockers = [
    schedule(async () => {
      await first.promise;
    }),
    schedule(async () => {
      await second.promise;
    }),
  ];
  const queued = schedule(async () => {
    queuedStarted = true;
  }, controller.signal).then(
    () => "resolved",
    (error: unknown) => error,
  );

  await flush();
  expect(pendingCount()).toBe(1);

  controller.abort("withdrawn");
  expect(await queued).toBe("withdrawn");
  expect(pendingCount()).toBe(0);

  first.resolve(undefined);
  second.resolve(undefined);
  await Promise.all(blockers);
  expect(queuedStarted).toBe(false);
  expect(pendingCount()).toBe(0);
});

test("a running render may finish after its signal aborts", async () => {
  const controller = new AbortController();
  const gate = deferred<void>();
  let observedSignal: AbortSignal | null = null;

  const task = schedule(async (signal) => {
    observedSignal = signal;
    await gate.promise;
    return "finished";
  }, controller.signal);

  await flush();
  controller.abort("late");
  gate.resolve(undefined);

  expect(await task).toBe("finished");
  expect(observedSignal).toBe(controller.signal);
  expect(pendingCount()).toBe(0);
});
