// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { classifyFile, parseCsv, prettyJson } from "./viewer-utils";

describe("classifyFile", () => {
  test("renders structured text formats as text", () => {
    for (const extension of [".jsonl", ".toml", ".ini", ".env"]) {
      expect(
        classifyFile({
          mime_type: "application/octet-stream",
          extension,
        }),
      ).toBe("text");
    }
  });

  test("keeps JSON, CSV, and Markdown on their dedicated viewers", () => {
    expect(
      classifyFile({ mime_type: "application/json", extension: ".json" }),
    ).toBe("json");
    expect(classifyFile({ mime_type: "text/csv", extension: ".csv" })).toBe(
      "csv",
    );
    expect(
      classifyFile({ mime_type: "text/markdown", extension: ".md" }),
    ).toBe("markdown");
  });

  test("recognizes uppercase spreadsheet and presentation extensions", () => {
    expect(
      classifyFile({
        mime_type: "application/octet-stream",
        extension: ".XLSX",
      }),
    ).toBe("spreadsheet");
    expect(
      classifyFile({
        mime_type: "application/octet-stream",
        extension: ".XLSM",
      }),
    ).toBe("spreadsheet");
    expect(
      classifyFile({
        mime_type: "application/octet-stream",
        extension: ".PPTX",
      }),
    ).toBe("pptx");
  });

  test("recognizes a macro-enabled workbook by MIME alone", () => {
    expect(
      classifyFile({
        mime_type: "application/vnd.ms-excel.sheet.macroEnabled.12",
        extension: "",
      }),
    ).toBe("spreadsheet");
  });
});

describe("parseCsv", () => {
  test("ignores commas inside quoted fields when detecting the delimiter", () => {
    const table = parseCsv(
      [
        "id;description",
        '1;"alpha, beta, gamma"',
        '2;"delta, epsilon; zeta"',
      ].join("\n"),
    );

    expect(table.headers).toEqual(["id", "description"]);
    expect(table.rows).toEqual([
      ["1", "alpha, beta, gamma"],
      ["2", "delta, epsilon; zeta"],
    ]);
  });

  test("allows whitespace before an opening quote", () => {
    const table = parseCsv('first,second\na, "b,c"');

    expect(table.rows).toEqual([["a", "b,c"]]);
  });
});

describe("prettyJson", () => {
  test("accepts JSON with a leading byte-order mark", () => {
    const result = prettyJson('\uFEFF{"title":"archive","count":2}');

    expect(result.valid).toBe(true);
    expect(result.formatted).toBe(
      ['{', '  "title": "archive",', '  "count": 2', "}"].join("\n"),
    );
  });
});

describe("every accepted upload type has a renderer", () => {
  // Mirrors backend ALLOWED_EXTENSIONS; browsers sometimes send a generic MIME,
  // so the extension alone must still pick the right renderer.
  const cases: ReadonlyArray<readonly [string, string, string]> = [
    [".md", "text/markdown", "markdown"],
    [".markdown", "application/octet-stream", "markdown"],
    [".txt", "text/plain", "text"],
    [".log", "application/octet-stream", "text"],
    [".csv", "text/csv", "csv"],
    [".json", "application/json", "json"],
    [".jsonl", "application/jsonl", "text"],
    [".toml", "application/toml", "text"],
    [".ini", "text/plain", "text"],
    [".env", "application/octet-stream", "text"],
    [".pdf", "application/pdf", "pdf"],
    [".docx", "application/octet-stream", "docx"],
    [".pptx", "application/octet-stream", "pptx"],
    [".xlsx", "application/octet-stream", "spreadsheet"],
    [".xlsm", "application/vnd.ms-excel.sheet.macroEnabled.12", "spreadsheet"],
    [".xls", "application/vnd.ms-excel", "spreadsheet"],
    [".ods", "application/vnd.oasis.opendocument.spreadsheet", "spreadsheet"],
    [".jpg", "image/jpeg", "image"],
    [".jpeg", "application/octet-stream", "image"],
    [".png", "image/png", "image"],
    [".webp", "image/webp", "image"],
  ];
  for (const [extension, mime, kind] of cases) {
    test(`${extension} (${mime}) -> ${kind}`, () => {
      expect(classifyFile({ extension, mime_type: mime })).toBe(kind);
    });
  }
});
