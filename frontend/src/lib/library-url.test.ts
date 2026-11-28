// @ts-expect-error Bun provides this module at test time.
import { describe, expect, test } from "bun:test";

import {
  legacyMemoryRedirect,
  libraryMemoriesUrl,
  libraryMemoryUrl,
  libraryNewMemoryUrl,
  parseLibraryMemoryUrl,
  parseLibraryUrl,
} from "./library-url";

describe("memory URLs", () => {
  test("round-trip the reader URL", () => {
    expect(libraryMemoryUrl(12)).toBe("/library/memories/12");
    expect(parseLibraryMemoryUrl(libraryMemoryUrl(12))).toEqual({
      kind: "read",
      rawId: "12",
    });
  });

  test("parse the index, new form, and an invalid id", () => {
    expect(parseLibraryMemoryUrl("/library/memories")).toEqual({ kind: "index" });
    expect(parseLibraryMemoryUrl("/library/memories/")).toEqual({ kind: "index" });
    expect(parseLibraryMemoryUrl("/library/memories/new")).toEqual({ kind: "new" });
    expect(parseLibraryMemoryUrl("/library/memories/abc")).toEqual({
      kind: "read",
      rawId: "abc",
    });
    expect(parseLibraryMemoryUrl("/library/memories/1/2")).toBeNull();
    expect(parseLibraryMemoryUrl("/library/files/3")).toBeNull();
  });

  test("build query strings", () => {
    expect(libraryMemoriesUrl({ q: "tea", status: null })).toBe(
      "/library/memories?q=tea",
    );
    expect(libraryNewMemoryUrl([3, 4])).toBe(
      "/library/memories/new?supersedes=3&supersedes=4",
    );
    expect(libraryNewMemoryUrl()).toBe("/library/memories/new");
  });

  test("redirect legacy memory URLs", () => {
    expect(legacyMemoryRedirect("/memory", "")).toBe("/library/memories");
    expect(legacyMemoryRedirect("/memory/", "")).toBe("/library/memories");
    expect(legacyMemoryRedirect("/memory/new", "?supersedes=3&supersedes=4")).toBe(
      "/library/memories/new?supersedes=3&supersedes=4",
    );
    expect(legacyMemoryRedirect("/memory/12", "?x=1")).toBe(
      "/library/memories/12?x=1",
    );
    expect(legacyMemoryRedirect("/memory/abc", "")).toBe("/library/memories/abc");
    expect(legacyMemoryRedirect("/library", "")).toBeNull();
    expect(legacyMemoryRedirect("/memoryx", "")).toBeNull();
  });

  test("memory paths are not folder or file routes", () => {
    expect(parseLibraryUrl("/library/memories")).toBeNull();
  });
});
