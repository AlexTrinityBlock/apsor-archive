// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { appendReasoningDelta } from "./reasoning-stream";
import type { ChatStreamSegment } from "./stream-reducer";

function segment(index: number, reasoning = ""): ChatStreamSegment {
  return {
    index,
    text: `answer ${index}`,
    toolCalls: [],
    reasoning,
    reasoningTokens: 0,
  };
}

describe("appendReasoningDelta", () => {
  test("appends to the newest segment without touching text or tools", () => {
    const segments = appendReasoningDelta(
      [segment(1, "first "), segment(2)],
      "second thought",
    );

    expect(segments).toHaveLength(2);
    expect(segments[0].reasoning).toBe("first ");
    expect(segments[1].reasoning).toBe("second thought");
    expect(segments[1].text).toBe("answer 2");
    expect(segments[1].toolCalls).toEqual([]);
  });

  test("keeps earlier segments intact across a later message start", () => {
    const first = appendReasoningDelta([segment(1)], "step one");
    const second = appendReasoningDelta(
      [...first, segment(2)],
      "step two",
    );

    expect(second.map((item) => item.reasoning)).toEqual([
      "step one",
      "step two",
    ]);
  });

  test("creates the first segment when the stream has none yet", () => {
    const segments = appendReasoningDelta([], "opening thought");

    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({
      index: 1,
      text: "",
      toolCalls: [],
      reasoning: "opening thought",
      reasoningTokens: 0,
    });
  });
});
