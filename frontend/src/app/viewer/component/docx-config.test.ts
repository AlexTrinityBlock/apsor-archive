// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { DOCX_FIT_GUTTER, docxFitScale } from "./docx-config";

describe("docxFitScale", () => {
  test("never scales a page up", () => {
    expect(docxFitScale(1200, 816)).toBe(1);
  });

  test("scales an A4/Letter page down to fit a phone-width frame", () => {
    const scale = docxFitScale(342, 816);
    expect(scale).toBeLessThan(1);
    expect(816 * scale).toBeLessThanOrEqual(342 - DOCX_FIT_GUTTER * 2 + 1);
  });

  test("falls back to 1 for unmeasured sizes", () => {
    expect(docxFitScale(0, 816)).toBe(1);
    expect(docxFitScale(342, 0)).toBe(1);
  });
});
