// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { citationLabel, parseCitationLabel } from "./types";
import {
  mergeWebSources,
  safeWebUrl,
  webDomainLabel,
  webRefNumber,
  webSourcesFromEntries,
} from "./web-sources";

function toolEntry(data: Record<string, unknown>): AgentEntrySchema {
  return { kind: "pi.tool-result", data } as unknown as AgentEntrySchema;
}

describe("web citation tokens", () => {
  test("parse and render [web:wN]", () => {
    expect(parseCitationLabel("[web:w3]")).toEqual({ kind: "web", id: 3, chunk: null });
    expect(parseCitationLabel("［web:w12］")).toEqual({ kind: "web", id: 12, chunk: null });
    expect(parseCitationLabel("[web:w0]")).toBeNull();
    expect(parseCitationLabel("[web:3]")).toBeNull();
    expect(citationLabel({ kind: "web", id: 7, chunk: null })).toBe("[web:w7]");
  });

  test("ref numbers and safe urls", () => {
    expect(webRefNumber("w4")).toBe(4);
    expect(webRefNumber("x4")).toBeNull();
    expect(safeWebUrl("javascript:alert(1)")).toBeNull();
    expect(safeWebUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(webDomainLabel("https://www.example.org/x?y=1")).toBe("example.org");
  });
});

describe("web sources", () => {
  test("collect from search and fetch results and live tools", () => {
    const map = webSourcesFromEntries(
      [
        toolEntry({
          tool: "web_search",
          results: [
            { ref: "w1", url: "https://example.com/tea", title: "Tea" },
            { ref: "w2", url: "ftp://example.com/x", title: "Bad" },
          ],
        }),
        toolEntry({ tool: "web_fetch", ref: "w1", url: "https://example.com/tea" }),
      ],
      [{ name: "web_fetch", data: { ref: "w3", url: "https://example.com/new" } }],
    );
    expect(map.get(1)).toEqual({ url: "https://example.com/tea", title: "Tea" });
    expect(map.has(2)).toBe(false);
    expect(map.get(3)).toEqual({ url: "https://example.com/new", title: null });
  });

  test("server rows win over transcript rows", () => {
    const merged = mergeWebSources(
      [{ ref: "w1", url: "https://example.com/canonical", title: "Canonical" }],
      new Map([[1, { url: "https://example.com/old", title: "Old" }]]),
    );
    expect(merged.get(1)).toEqual({
      url: "https://example.com/canonical",
      title: "Canonical",
    });
  });
});
