// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import type { AgentStreamEvent } from "../../../apis/agent-stream";
import {
  applyStreamEvent,
  applyStreamEvents,
  coalesceDeltas,
  createStreamView,
  isDeltaEvent,
} from "./stream-reducer";

const start: AgentStreamEvent = {
  type: "message_start",
  data: { entry_id: null, kind: "pi.message", role: "assistant" },
};

function text(delta: string): AgentStreamEvent {
  return { type: "message_delta", data: { entry_id: null, delta } };
}

function reasoning(delta: string): AgentStreamEvent {
  return { type: "reasoning_delta", data: { entry_id: null, delta } };
}

function toolStart(id: string): AgentStreamEvent {
  return {
    type: "tool_start",
    data: { entry_id: null, tool_call_id: id, name: "search_knowledge", arguments: {} },
  };
}

describe("stream reducer", () => {
  test("keeps earlier prose when a second step starts", () => {
    const seed = createStreamView(1, "hi", [], null);
    const state = [start, text("one"), toolStart("a"), start, text("two")].reduce(
      applyStreamEvent,
      seed,
    );
    expect(state.segments.map((segment) => segment.text)).toEqual(["one", "two"]);
    expect(state.segments[0]?.toolCalls.map((tool) => tool.id)).toEqual(["a"]);
    expect(state.assistantText).toBe("one\n\ntwo");
  });

  test("batched application matches event-by-event application", () => {
    const events = [
      start,
      reasoning("th"),
      reasoning("ink"),
      text("He"),
      text("llo"),
      toolStart("a"),
      start,
      text("Bye"),
    ];
    const seed = createStreamView(1, "hi", [], null);
    const oneByOne = events.reduce(applyStreamEvent, seed);
    const batched = applyStreamEvents(seed, events);
    expect(batched.segments).toEqual(oneByOne.segments);
    expect(batched.assistantText).toBe(oneByOne.assistantText);
  });

  test("maps run_end statuses", () => {
    const seed = createStreamView(1, "hi", [], null);
    const done = applyStreamEvent(seed, {
      type: "run_end",
      data: { run_id: 3, status: "cancelled" },
    });
    expect(done.status).toBe("done");
    const failed = applyStreamEvent(seed, {
      type: "run_end",
      data: { run_id: 3, status: "failed" },
    });
    expect(failed.status).toBe("failed");
  });
});

describe("delta coalescing", () => {
  test("merges only adjacent deltas of one kind", () => {
    const merged = coalesceDeltas([
      text("a"),
      text("b"),
      reasoning("x"),
      reasoning("y"),
      text("c"),
      toolStart("t"),
      text("d"),
    ]);
    expect(merged.map((event) => event.type)).toEqual([
      "message_delta",
      "reasoning_delta",
      "message_delta",
      "tool_start",
      "message_delta",
    ]);
    const first = merged[0];
    expect(first?.type === "message_delta" ? first.data.delta : null).toBe("ab");
  });

  test("identifies token-sized events", () => {
    expect(isDeltaEvent(text("a"))).toBe(true);
    expect(isDeltaEvent(reasoning("a"))).toBe(true);
    expect(isDeltaEvent(start)).toBe(false);
  });
});
