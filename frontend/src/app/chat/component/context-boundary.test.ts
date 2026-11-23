// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { entryIdRange } from "./ContextBoundaryCard";

describe("entryIdRange", () => {
  test("returns the first and last ids of a non-empty list", () => {
    expect(entryIdRange([4331, 4332, 4350])).toEqual({
      first: 4331,
      last: 4350,
    });
    expect(entryIdRange([4331])).toEqual({ first: 4331, last: 4331 });
  });

  test("returns null for empty or malformed lists", () => {
    expect(entryIdRange(null)).toBeNull();
    expect(entryIdRange([])).toBeNull();
    expect(entryIdRange(["4331"])).toBeNull();
    expect(entryIdRange([4331, "oops"])).toBeNull();
  });
});
