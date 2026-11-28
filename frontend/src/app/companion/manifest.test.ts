// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  characterFrameUrls,
  frameAtStep,
  parseManifest,
  parsePresetIndex,
  resolveClip,
  resolveFrameUrl,
} from "./manifest";

const BASE = "/companions/elise";

const manifest = {
  schema: 1,
  id: "elise",
  name: "Elise",
  gender: "female",
  palette: { accent: "#c9a24a" },
  anchor: { x: 0.48, y: 0.05 },
  size: { width: 384, height: 576 },
  actions: {
    idle: { frames: ["idle.webp"], fps: 0, loop: true },
    reading: { frames: ["reading-1.webp", "reading-2.webp"], fps: 4, loop: true },
    success: { frames: ["../escape.webp", "https://evil.example/x.webp"] },
    dance: { frames: ["dance.webp"] },
  },
};

describe("resolveFrameUrl", () => {
  test("accepts plain names, api paths, and blobs only", () => {
    expect(resolveFrameUrl(BASE, "idle.webp")).toBe("/companions/elise/idle.webp");
    expect(resolveFrameUrl(BASE, "/api/v1/companions/3/frames/9")).toBe(
      "/api/v1/companions/3/frames/9",
    );
    expect(resolveFrameUrl(BASE, "blob:http://x/abc")).toBe("blob:http://x/abc");
    expect(resolveFrameUrl(BASE, "../idle.webp")).toBeNull();
    expect(resolveFrameUrl(BASE, "https://evil.example/a.webp")).toBeNull();
    expect(resolveFrameUrl(BASE, "/api/../etc")).toBeNull();
    expect(resolveFrameUrl(BASE, 4)).toBeNull();
  });
});

describe("parseManifest", () => {
  test("parses a valid manifest and drops unsafe or unknown clips", () => {
    const character = parseManifest(manifest, BASE);
    expect(character).not.toBeNull();
    expect(character?.name).toBe("Elise");
    expect(character?.gender).toBe("female");
    expect(character?.accent).toBe("#c9a24a");
    expect(character?.portrait).toBe("/companions/elise/portrait.avif");
    expect(Object.keys(character?.actions ?? {}).sort()).toEqual(["idle", "reading"]);
    expect(character?.actions.reading?.fps).toBe(4);
  });

  test("rejects manifests without idle or with an unsafe id", () => {
    expect(parseManifest({ ...manifest, actions: { reading: manifest.actions.reading } }, BASE))
      .toBeNull();
    expect(parseManifest({ ...manifest, id: "../x" }, BASE)).toBeNull();
    expect(parseManifest(null, BASE)).toBeNull();
  });

  test("defaults bad accent and size, and ignores a legacy string anchor", () => {
    const character = parseManifest(
      { id: "x", actions: { idle: { frames: ["idle.webp"] } }, palette: { accent: "red" }, anchor: { x: 4 } },
      "/companions/x",
    );
    expect(character?.accent).toBe("#b8933f");
    expect(character).not.toHaveProperty("anchor");
    expect(character?.width).toBe(384);
    expect(character?.gender).toBe("unspecified");
  });

  test("multi-frame clips get a default fps", () => {
    const character = parseManifest(
      { id: "x", actions: { idle: { frames: ["a.webp", "b.webp"] } } },
      "/companions/x",
    );
    expect(character?.actions.idle?.fps).toBe(6);
  });
});

describe("resolveClip", () => {
  test("walks the fallback chain to idle", () => {
    const character = parseManifest(manifest, BASE);
    if (character === null) {
      throw new Error("fixture must parse");
    }
    expect(resolveClip(character, "reading").action).toBe("reading");
    expect(resolveClip(character, "searching").action).toBe("reading");
    expect(resolveClip(character, "sleeping").action).toBe("idle");
    expect(characterFrameUrls(character)).toEqual([
      "/companions/elise/idle.webp",
      "/companions/elise/reading-1.webp",
      "/companions/elise/reading-2.webp",
    ]);
  });
});

describe("parsePresetIndex", () => {
  test("accepts arrays and wrapped lists, dedupes, drops unsafe ids", () => {
    expect(parsePresetIndex(["a", "a", "../b", "c"]).map((ref) => ref.id)).toEqual(["a", "c"]);
    expect(
      parsePresetIndex({ presets: [{ id: "elise", name: "Elise", gender: "female" }] }),
    ).toEqual([{ id: "elise", name: "Elise", gender: "female" }]);
    expect(parsePresetIndex({ characters: ["z"] })[0]?.id).toBe("z");
    expect(parsePresetIndex({ nope: true })).toEqual([]);
  });
});

describe("frameAtStep", () => {
  const clip = (count: number, patch: { loop?: boolean; pingpong?: boolean } = {}) => ({
    frames: Array.from({ length: count }, (_, index) => `f${index}.avif`),
    fps: 5,
    loop: patch.loop ?? true,
    pingpong: patch.pingpong ?? false,
  });

  test("wraps, bounces, and holds", () => {
    expect([0, 1, 2, 3, 4].map((step) => frameAtStep(clip(3), step))).toEqual([0, 1, 2, 0, 1]);
    expect(
      [0, 1, 2, 3, 4, 5].map((step) => frameAtStep(clip(3, { pingpong: true }), step)),
    ).toEqual([0, 1, 2, 1, 0, 1]);
    expect(frameAtStep(clip(3, { loop: false }), 9)).toBe(2);
    expect(frameAtStep(clip(1), 9)).toBe(0);
  });

  test("parses pingpong only for multi-frame clips; AVIF paths pass through", () => {
    const character = parseManifest(
      {
        id: "x",
        portrait: "portrait.avif",
        actions: {
          idle: { frames: ["idle-1.avif", "idle-2.avif", "idle-3.avif"], fps: 5, pingpong: true },
          thinking: { frames: ["thinking.avif"], pingpong: true },
        },
      },
      "/companions/x",
    );
    expect(character?.actions.idle?.pingpong).toBe(true);
    expect(character?.actions.thinking?.pingpong).toBe(false);
    expect(character?.actions.idle?.frames[0]).toBe("/companions/x/idle-1.avif");
    expect(character?.portrait).toBe("/companions/x/portrait.avif");
  });
});
