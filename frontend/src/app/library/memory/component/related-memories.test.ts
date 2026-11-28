// @ts-expect-error Bun provides this module at test time.
import { describe, expect, test } from "bun:test";

import {
  clipRelatedPreview,
  orderRelatedReasons,
  relatedReasonKey,
} from "./related-memories";

describe("related memories helpers", () => {
  test("order reasons and drop unknown values", () => {
    expect(orderRelatedReasons(["nearby", "bogus", "similar", "similar"])).toEqual([
      "similar",
      "nearby",
    ]);
    expect(orderRelatedReasons([])).toEqual([]);
  });

  test("map reasons to translation keys", () => {
    expect(relatedReasonKey("summary")).toBe("memory.related.reason.summary");
  });

  test("clip previews at a word boundary", () => {
    expect(clipRelatedPreview("  short   text ")).toBe("short text");
    const long = "word ".repeat(60);
    const clipped = clipRelatedPreview(long, 40);
    expect(clipped.endsWith("…")).toBe(true);
    expect(clipped.length).toBeLessThanOrEqual(41);
    expect(clipped).not.toContain("  ");
  });
});
