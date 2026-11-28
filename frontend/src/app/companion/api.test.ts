// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import type { CompanionSchema } from "../generated-apis-types/schemas";
import {
  companionIdFromRef,
  companionRef,
  customCharacter,
  customCompanionId,
} from "./api";

function frame(id: number, action: string, position: number) {
  return {
    id,
    action,
    position,
    width: 384,
    height: 576,
    mime_type: "image/avif",
    size_bytes: 1000,
    version: "abc",
    url: `/api/v1/companions/7/frames/${id}/image?v=abc`,
  };
}

function companion(frames: ReturnType<typeof frame>[]): CompanionSchema {
  return {
    id: 7,
    name: "Ink",
    gender: "other",
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
    frames,
  } as CompanionSchema;
}

describe("companion refs", () => {
  test("round-trips preset and custom selections", () => {
    expect(companionRef({ id: "vellum" })).toBe("preset:vellum");
    expect(companionRef({ id: "custom-12" })).toBe("custom:12");
    expect(companionIdFromRef("preset:vellum")).toBe("vellum");
    expect(companionIdFromRef("custom:12")).toBe("custom-12");
    expect(companionIdFromRef("custom:abc")).toBeNull();
    expect(companionIdFromRef(null)).toBeNull();
    expect(customCompanionId("custom-12")).toBe(12);
    expect(customCompanionId("vellum")).toBeNull();
  });
});

describe("customCharacter", () => {
  test("groups frames by action in position order", () => {
    const character = customCharacter(
      companion([frame(3, "idle", 1), frame(2, "idle", 0), frame(4, "thinking", 0)]),
    );
    expect(character?.id).toBe("custom-7");
    expect(character?.gender).toBe("unspecified");
    expect(character?.actions.idle?.frames).toEqual([
      "/api/v1/companions/7/frames/2/image?v=abc",
      "/api/v1/companions/7/frames/3/image?v=abc",
    ]);
    expect(character?.actions.idle?.fps).toBeGreaterThan(0);
    expect(character?.actions.thinking?.fps).toBe(0);
    expect(character?.portrait).toBe("/api/v1/companions/7/frames/2/image?v=abc");
  });

  test("borrows the first action as idle and skips empty companions", () => {
    const character = customCharacter(companion([frame(5, "reading", 0)]));
    expect(character?.actions.idle?.frames).toEqual([
      "/api/v1/companions/7/frames/5/image?v=abc",
    ]);
    expect(customCharacter(companion([]))).toBeNull();
  });
});
