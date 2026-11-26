// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import type { Translate } from "../i18n";
import { toolStepLabel } from "./tool-label";

const t = ((key: string) => key) as Translate;

describe("toolStepLabel", () => {
  test("names the presented resource instead of the raw tool", () => {
    expect(toolStepLabel("present_resource", "memory", t)).toBe(
      "chat.resource.presentedMemory",
    );
    expect(toolStepLabel("present_resource", "file", t)).toBe(
      "chat.resource.presentedFile",
    );
  });

  test("keeps the technical tool name when no resource type is known", () => {
    expect(toolStepLabel("present_resource", null, t)).toBe("present_resource");
    expect(toolStepLabel("read_file", "file", t)).toBe("read_file");
  });

  test("falls back to the generic result label for a missing tool", () => {
    expect(toolStepLabel(null, null, t)).toBe("chat.tool.resultFallback");
  });
});
