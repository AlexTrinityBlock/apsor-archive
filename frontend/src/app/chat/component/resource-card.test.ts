// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { textThumbnailBadge } from "./ResourceCard";

describe("textThumbnailBadge", () => {
  test("uses the presented extension for known text formats", () => {
    expect(textThumbnailBadge("events.jsonl")).toBe("JSONL");
    expect(textThumbnailBadge("settings.toml")).toBe("TOML");
    expect(textThumbnailBadge("settings.ini")).toBe("INI");
    expect(textThumbnailBadge(".env")).toBe("ENV");
    expect(textThumbnailBadge("server.log")).toBe("LOG");
    expect(textThumbnailBadge("notes.txt")).toBe("TXT");
  });

  test("keeps the generic badge for unknown or missing text names", () => {
    expect(textThumbnailBadge("LICENSE")).toBe("TXT");
    expect(textThumbnailBadge("data.unknown")).toBe("TXT");
    expect(textThumbnailBadge(null)).toBe("TXT");
  });
});
