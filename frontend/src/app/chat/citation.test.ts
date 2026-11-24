// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { citationLabel, parseCitationLabel } from "./types";

describe("parseCitationLabel", () => {
  test("reads ASCII citation tokens", () => {
    expect(parseCitationLabel("[memory:147]")).toEqual({
      kind: "memory",
      id: 147,
      chunk: null,
    });
    expect(parseCitationLabel("  [file:93#2]  ")).toEqual({
      kind: "file",
      id: 93,
      chunk: 2,
    });
    expect(parseCitationLabel("[history:12]")).toEqual({
      kind: "history",
      id: 12,
      chunk: null,
    });
  });

  test("reads full-width brackets from pasted briefs and IMEs", () => {
    expect(parseCitationLabel("［memory:147］")).toEqual({
      kind: "memory",
      id: 147,
      chunk: null,
    });
    expect(parseCitationLabel("［file:93#2］")).toEqual({
      kind: "file",
      id: 93,
      chunk: 2,
    });
    expect(parseCitationLabel("［summary:4］")).toEqual({
      kind: "summary",
      id: 4,
      chunk: null,
    });
    expect(parseCitationLabel("［history:12］")).toEqual({
      kind: "history",
      id: 12,
      chunk: null,
    });
  });

  test("rejects invalid or chunked history tokens", () => {
    expect(parseCitationLabel("[history:12#1]")).toBeNull();
    expect(parseCitationLabel("[memory:0]")).toBeNull();
    expect(parseCitationLabel("[memory:not-a-number]")).toBeNull();
  });
});

describe("citationLabel", () => {
  test("writes the canonical ASCII form", () => {
    expect(citationLabel({ kind: "memory", id: 147, chunk: null })).toBe(
      "[memory:147]",
    );
    expect(citationLabel({ kind: "file", id: 93, chunk: 2 })).toBe(
      "[file:93#2]",
    );
  });
});
