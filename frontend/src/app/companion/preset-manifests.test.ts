// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";
// @ts-expect-error -- Node built-ins are available under Bun; the frontend tsconfig does not load @types/node.
import { existsSync, readFileSync } from "node:fs";

import { COMPANION_ACTIONS } from "./actions";
import { frameAtStep, parseManifest, parsePresetIndex } from "./manifest";

const PUBLIC_ROOT = new URL("../../../public/companions/", import.meta.url);

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(new URL(path, PUBLIC_ROOT), "utf8")) as unknown;
}

describe("shipped preset manifests", () => {
  const presets = parsePresetIndex(readJson("index.json"));

  test("the index lists six presets, half female and half male", () => {
    expect(presets.map((preset) => preset.id)).toEqual([
      "vellum",
      "atlas",
      "herbaria",
      "horologe",
      "nocturne",
      "quill",
    ]);
    expect(presets.filter((preset) => preset.gender === "female")).toHaveLength(3);
    expect(presets.filter((preset) => preset.gender === "male")).toHaveLength(3);
  });

  test("every manifest parses with all actions and existing frame files", () => {
    for (const preset of presets) {
      const base = `/companions/${preset.id}`;
      const character = parseManifest(readJson(`${preset.id}/manifest.json`), base);
      expect(character?.id).toBe(preset.id);
      expect(Object.keys(character?.actions ?? {}).sort()).toEqual([...COMPANION_ACTIONS].sort());
      expect(character?.portrait).toBe(`${base}/portrait.avif`);
      const files = [
        character?.portrait ?? "",
        ...Object.values(character?.actions ?? {}).flatMap((clip) => clip?.frames ?? []),
      ];
      for (const file of files) {
        const relative = file.slice("/companions/".length);
        expect(existsSync(new URL(relative, PUBLIC_ROOT))).toBe(true);
      }
    }
  });

  test("multi-frame actions ping-pong through their frames", () => {
    const character = parseManifest(readJson("vellum/manifest.json"), "/companions/vellum");
    const idle = character?.actions.idle;
    expect(idle?.frames).toHaveLength(3);
    expect(idle?.pingpong).toBe(true);
    expect(idle?.fps).toBeGreaterThan(0);
    if (idle === undefined) {
      return;
    }
    expect([0, 1, 2, 3, 4, 5].map((step) => frameAtStep(idle, step))).toEqual([0, 1, 2, 1, 0, 1]);
    for (const action of ["thinking", "speaking", "sleeping", "success", "searching"] as const) {
      expect(character?.actions[action]?.frames.length).toBeGreaterThan(1);
      expect(character?.actions[action]?.pingpong).toBe(true);
    }
    expect(character?.actions.greet?.frames).toHaveLength(1);
    expect(character?.actions.greet?.pingpong).toBe(false);
  });
});
