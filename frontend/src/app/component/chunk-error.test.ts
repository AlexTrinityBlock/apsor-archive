// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import { importWithRetry, isChunkError } from "./chunk-error";

test("chunk load failures from every major browser are recognised", () => {
  expect(isChunkError(new TypeError("Failed to fetch dynamically imported module: /assets/x.js"))).toBe(true);
  expect(isChunkError(new TypeError("Importing a module script failed."))).toBe(true);
  expect(isChunkError(new TypeError("error loading dynamically imported module"))).toBe(true);
  expect(isChunkError(new Error("Unable to preload CSS for /assets/x.css"))).toBe(true);
  expect(isChunkError(new Error("Cannot read properties of undefined"))).toBe(false);
  expect(isChunkError(null)).toBe(false);
});

test("a chunk failure is retried once, other errors are not", async () => {
  let calls = 0;
  const flaky = () => {
    calls += 1;
    return calls === 1
      ? Promise.reject(new TypeError("Failed to fetch dynamically imported module"))
      : Promise.resolve("ok");
  };
  expect(await importWithRetry(flaky)).toBe("ok");
  expect(calls).toBe(2);

  let other = 0;
  const broken = () => {
    other += 1;
    return Promise.reject(new Error("boom"));
  };
  await expect(importWithRetry(broken)).rejects.toThrow("boom");
  expect(other).toBe(1);
});
