// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { DEFAULT_PREFERENCE, readOpacityMode, readPreference, readSize } from "./preference";

describe("companion preference", () => {
  test("defaults to full size and auto opacity", () => {
    expect(DEFAULT_PREFERENCE.size).toBe("full");
    expect(DEFAULT_PREFERENCE.opacityMode).toBe("opaque");
  });

  test("reads stored size and opacity, falling back on bad values", () => {
    const stored = readPreference({ enabled: true, size: "compact", opacityMode: "opaque" });
    expect(stored.size).toBe("compact");
    expect(stored.opacityMode).toBe("opaque");
    expect(readSize("huge")).toBe("full");
    expect(readOpacityMode(undefined)).toBe("opaque");
    // Older stored preferences without the new fields keep working.
    expect(readPreference({ enabled: false, motion: "off" })).toMatchObject({
      enabled: false,
      motion: "off",
      size: "full",
      opacityMode: "auto",
    });
  });
});
