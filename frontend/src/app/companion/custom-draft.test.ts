// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  MAX_FRAMES_PER_ACTION,
  MAX_FRAME_BYTES,
  draftCharacter,
  draftFrameCount,
  moveFrame,
  screenFrames,
  type DraftFrame,
} from "./custom-draft";

function file(name: string, type: string, size = 10): File {
  return { name, type, size } as File;
}

function frame(id: string): DraftFrame {
  return { id, file: file(`${id}.png`, "image/png"), url: `blob:${id}` };
}

describe("screenFrames", () => {
  test("accepts images, rejects other types, big files, and overflow", () => {
    const result = screenFrames(
      [
        file("a.png", "image/png"),
        file("b.avif", "image/avif"),
        file("c.gif", "image/gif"),
        file("d.webp", "image/webp", MAX_FRAME_BYTES + 1),
      ],
      0,
    );
    expect(result.accepted.map((item) => item.name)).toEqual(["a.png", "b.avif"]);
    expect(result.rejected).toEqual([
      { kind: "type", file: "c.gif" },
      { kind: "size", file: "d.webp" },
    ]);
    const full = screenFrames(
      [file("x.png", "image/png"), file("y.png", "image/png")],
      MAX_FRAMES_PER_ACTION - 1,
    );
    expect(full.accepted).toHaveLength(1);
    expect(full.rejected).toEqual([{ kind: "count" }]);
  });
});

describe("moveFrame", () => {
  test("moves within bounds only", () => {
    expect(moveFrame(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveFrame(["a", "b", "c"], 2, 1)).toEqual(["a", "b", "c"]);
    expect(moveFrame(["a"], 5, -1)).toEqual(["a"]);
  });
});

describe("draftCharacter", () => {
  test("needs an idle frame and keeps blob URLs", () => {
    expect(draftCharacter("x", "female", {})).toBeNull();
    const character = draftCharacter(" Mira ", "female", {
      idle: { frames: [frame("i1"), frame("i2")], fps: 5 },
      reading: { frames: [frame("r1")], fps: 8 },
      writing: { frames: [], fps: 6 },
    });
    expect(character?.name).toBe("Mira");
    expect(character?.actions.idle?.frames).toEqual(["blob:i1", "blob:i2"]);
    expect(character?.actions.idle?.fps).toBe(5);
    expect(character?.actions.reading?.fps).toBe(0);
    expect(character?.actions.writing).toBeUndefined();
    expect(character?.portrait).toBe("blob:i1");
    expect(
      draftFrameCount({ idle: { frames: [frame("a"), frame("b")], fps: 6 }, held: { frames: [frame("c")], fps: 6 } }),
    ).toBe(3);
  });
});
