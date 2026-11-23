// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { beforeEach, expect, test } from "bun:test";

import {
  getThumb,
  resetThumbs,
  setThumbFailed,
  setThumbImage,
} from "./thumb-cache";

beforeEach(() => {
  resetThumbs();
});

test("a rendered image is returned with its data URL", () => {
  setThumbImage("1:2026-01-01", "data:image/webp;base64,AAAA");
  expect(getThumb("1:2026-01-01")).toEqual({
    kind: "image",
    dataUrl: "data:image/webp;base64,AAAA",
  });
});

test("a failure marker is remembered for the session", () => {
  setThumbFailed("2:2026-01-01");
  expect(getThumb("2:2026-01-01")).toEqual({ kind: "failed" });
});

test("an unknown key has no entry", () => {
  expect(getThumb("missing")).toBeUndefined();
});

test("the cache evicts the least recently used entry at 200 items", () => {
  for (let index = 0; index < 200; index += 1) {
    setThumbImage(`key-${index}`, `data:image/webp;base64,${index}`);
  }

  // Touch the oldest entry so the next insert must evict the second key.
  expect(getThumb("key-0")).toEqual({
    kind: "image",
    dataUrl: "data:image/webp;base64,0",
  });
  setThumbImage("key-200", "data:image/webp;base64,200");

  expect(getThumb("key-0")).toBeDefined();
  expect(getThumb("key-1")).toBeUndefined();
  expect(getThumb("key-200")).toBeDefined();
});

test("failure markers count toward the cap", () => {
  for (let index = 0; index < 200; index += 1) {
    setThumbFailed(`failed-${index}`);
  }
  setThumbFailed("failed-200");
  expect(getThumb("failed-0")).toBeUndefined();
  expect(getThumb("failed-1")).toBeDefined();
});

test("replacing an entry does not duplicate it", () => {
  setThumbFailed("same");
  setThumbImage("same", "data:image/webp;base64,BBBB");
  expect(getThumb("same")).toEqual({
    kind: "image",
    dataUrl: "data:image/webp;base64,BBBB",
  });
});

test("reset drops every entry", () => {
  setThumbImage("one", "data:image/webp;base64,AAAA");
  setThumbFailed("two");
  resetThumbs();
  expect(getThumb("one")).toBeUndefined();
  expect(getThumb("two")).toBeUndefined();
});
