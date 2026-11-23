// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { beforeEach, expect, test } from "bun:test";

import {
  getMarkdownSnippet,
  resetMarkdownSnippets,
  setMarkdownSnippet,
  setMarkdownSnippetFailed,
} from "./markdown-snippet-cache";

beforeEach(() => {
  resetMarkdownSnippets();
});

test("a cached snippet is returned with its text", () => {
  setMarkdownSnippet("7:2026-01-01", "# Title\n\nBody");
  expect(getMarkdownSnippet("7:2026-01-01")).toEqual({
    kind: "text",
    text: "# Title\n\nBody",
  });
});

test("a failure marker is remembered for the session", () => {
  setMarkdownSnippetFailed("8:2026-01-01");
  expect(getMarkdownSnippet("8:2026-01-01")).toEqual({ kind: "failed" });
});

test("an unknown key has no entry", () => {
  expect(getMarkdownSnippet("missing")).toBeUndefined();
});

test("the cache evicts the least recently used snippet at 200 items", () => {
  for (let index = 0; index < 200; index += 1) {
    setMarkdownSnippet(`key-${index}`, `text ${index}`);
  }

  // Touch the oldest entry so the next insert must evict the second key.
  expect(getMarkdownSnippet("key-0")).toEqual({
    kind: "text",
    text: "text 0",
  });
  setMarkdownSnippet("key-200", "text 200");

  expect(getMarkdownSnippet("key-0")).toBeDefined();
  expect(getMarkdownSnippet("key-1")).toBeUndefined();
  expect(getMarkdownSnippet("key-200")).toBeDefined();
});

test("failure markers count toward the cap", () => {
  for (let index = 0; index < 200; index += 1) {
    setMarkdownSnippetFailed(`failed-${index}`);
  }
  setMarkdownSnippetFailed("failed-200");
  expect(getMarkdownSnippet("failed-0")).toBeUndefined();
  expect(getMarkdownSnippet("failed-1")).toBeDefined();
});

test("replacing an entry does not duplicate it", () => {
  setMarkdownSnippetFailed("same");
  setMarkdownSnippet("same", "recovered");
  expect(getMarkdownSnippet("same")).toEqual({
    kind: "text",
    text: "recovered",
  });
});

test("reset drops every entry", () => {
  setMarkdownSnippet("one", "first");
  setMarkdownSnippetFailed("two");
  resetMarkdownSnippets();
  expect(getMarkdownSnippet("one")).toBeUndefined();
  expect(getMarkdownSnippet("two")).toBeUndefined();
});
