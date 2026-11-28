// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import { thumbCacheKey, thumbKindFor } from "./thumb-kind";

test("image extensions are recognised regardless of case", () => {
  for (const extension of ["jpg", "JPG", "jpeg", "png", "webp", "gif", "avif"]) {
    expect(thumbKindFor(`/photos/holiday.${extension}`)).toBe("image");
  }
});

test("document extensions map to their renderer", () => {
  expect(thumbKindFor("/papers/report.pdf")).toBe("pdf");
  expect(thumbKindFor("/papers/REPORT.PDF")).toBe("pdf");
  expect(thumbKindFor("/notes/letter.docx")).toBe("docx");
  expect(thumbKindFor("/notes/letter.DOCX")).toBe("docx");
  expect(thumbKindFor("/slides/deck.pptx")).toBe("pptx");
  expect(thumbKindFor("/slides/deck.Pptx")).toBe("pptx");
});

test("spreadsheet extensions map to the xlsx preview regardless of case", () => {
  for (const extension of ["xlsx", "xls", "xlsm", "ods", "XLSX", "Xlsm", "ODS"]) {
    expect(thumbKindFor(`/tables/budget.${extension}`)).toBe("xlsx");
  }
});

test("markdown extensions map to the rendered page", () => {
  expect(thumbKindFor("/notes/readme.md")).toBe("markdown");
  expect(thumbKindFor("/notes/README.MD")).toBe("markdown");
  expect(thumbKindFor("/notes/guide.markdown")).toBe("markdown");
  expect(thumbKindFor("/notes/guide.Markdown")).toBe("markdown");
});

test("plain-text extensions show a text page", () => {
  for (const extension of ["txt", "log", "csv", "json", "jsonl", "toml", "ini", "env", "TXT"]) {
    expect(thumbKindFor(`/notes/data.${extension}`)).toBe("text");
  }
});

test("nested folders use the real basename, not a directory dot", () => {
  expect(thumbKindFor("/archive.v2/photos/cover.png")).toBe("image");
  expect(thumbKindFor("/archive.v2/notes/summary.pdf")).toBe("pdf");
  expect(thumbKindFor("/archive.v2/tables/budget.xlsx")).toBe("xlsx");
  expect(thumbKindFor("/archive.v2/notes/readme.md")).toBe("markdown");
  expect(thumbKindFor("/archive.v2/notes/summary")).toBe("file");
});

test("unknown, missing, and trailing-dot extensions fall back to file", () => {
  expect(thumbKindFor("/notes/readme.xyz")).toBe("file");
  expect(thumbKindFor("/notes/readme")).toBe("file");
  expect(thumbKindFor("/notes/readme.")).toBe("file");
  expect(thumbKindFor("")).toBe("file");
});

test("a document name with a dot in the folder is still classified by the file", () => {
  expect(thumbKindFor("/2024.notes/final.txt")).toBe("text");
  expect(thumbKindFor("/2024.notes/final.pdf")).toBe("pdf");
});

test("the cache key changes when the stored version changes", () => {
  const first = { file_id: 42, update_time: "2026-01-01T00:00:00Z" };
  const replacement = { file_id: 42, update_time: "2026-02-01T00:00:00Z" };
  expect(thumbCacheKey(first)).toBe("42:2026-01-01T00:00:00Z");
  expect(thumbCacheKey(replacement)).not.toBe(thumbCacheKey(first));
  expect(thumbCacheKey({ ...first })).toBe(thumbCacheKey(first));
});
