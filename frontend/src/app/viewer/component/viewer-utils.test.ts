// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { classifyFile } from "./viewer-utils";

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
});
