// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { buildTimeline } from "./timeline";

interface Call {
  readonly id: string;
  readonly name: string;
}

/** A persisted assistant entry carrying one text step and its tool calls. */
function assistant(
  id: number,
  text: string,
  calls: readonly Call[] = [],
): AgentEntrySchema {
  return {
    by_run_id: 1,
    commit_seq: id,
    conversation_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    data: { step: id },
    edits: null,
    head_entry_id: null,
    id,
    kind: "pi.assistant",
    model: [
      {
        role: "assistant",
        content: text,
        tool_calls: calls.map((call) => ({
          id: call.id,
          type: "function",
          function: { name: call.name, arguments: "{}" },
        })),
      },
    ],
  };
}

/** A persisted tool result, including its structured preview payload. */
function toolResult(id: number, callId: string): AgentEntrySchema {
  return {
    by_run_id: 1,
    commit_seq: id,
    conversation_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    data: {
      tool: "web_search",
      status: "ok",
      arguments: { query: "archive" },
      duration_ms: 12,
    },
    edits: null,
    head_entry_id: null,
    id,
    kind: "pi.tool-result",
    model: [{ role: "tool", tool_call_id: callId, content: "<tool_result />" }],
  };
}

function boundary(id: number, kind: "pi.compaction" | "pi.reset"): AgentEntrySchema {
  return {
    by_run_id: 1,
    commit_seq: id,
    conversation_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    data: { reason: "manual" },
    edits: null,
    head_entry_id: null,
    id,
    kind,
    model: null,
  };
}

test("assistant prose, tool result, and the next assistant prose stay in order", () => {
  const timeline = buildTimeline([
    assistant(1, "First pass.", [{ id: "call-1", name: "web_search" }]),
    toolResult(2, "call-1"),
    assistant(3, "Second pass."),
  ]);

  expect(timeline.map((item) => item.kind)).toEqual([
    "assistant",
    "assistant",
  ]);
  const first = timeline[0];
  const second = timeline[1];
  expect(first.kind).toBe("assistant");
  expect(second.kind).toBe("assistant");
  if (first.kind !== "assistant" || second.kind !== "assistant") {
    return;
  }
  expect(first.text).toBe("First pass.");
  expect(first.results.map((result) => result.entry.id)).toEqual([2]);
  expect(first.step).toBe(1);
  expect(second.text).toBe("Second pass.");
  expect(second.results).toHaveLength(0);
  expect(second.step).toBe(3);
});

test("multiple tool results after one assistant step are all kept", () => {
  const timeline = buildTimeline([
    assistant(1, "Collect both.", [
      { id: "call-1", name: "web_search" },
      { id: "call-2", name: "web_fetch" },
    ]),
    toolResult(2, "call-1"),
    toolResult(3, "call-2"),
  ]);

  expect(timeline).toHaveLength(1);
  const step = timeline[0];
  expect(step.kind).toBe("assistant");
  if (step.kind !== "assistant") {
    return;
  }
  expect(step.results.map((result) => result.entry.id)).toEqual([2, 3]);
  expect(step.results.map((result) => result.call?.name)).toEqual([
    "web_search",
    "web_fetch",
  ]);
});

test("a tool result with no matching call is not dropped", () => {
  const timeline = buildTimeline([
    assistant(1, "Only prose."),
    toolResult(2, "missing-call"),
    toolResult(3, "another-missing-call"),
  ]);

  const step = timeline[0];
  expect(step.kind).toBe("assistant");
  if (step.kind !== "assistant") {
    return;
  }
  expect(step.results.map((result) => result.entry.id)).toEqual([2, 3]);
  expect(step.results.map((result) => result.call)).toEqual([null, null]);

  const orphan = buildTimeline([toolResult(4, "orphan-call")]);
  expect(orphan).toHaveLength(1);
  expect(orphan[0].kind).toBe("entry");
  expect(orphan[0].entry.id).toBe(4);
});

test("a compaction or reset boundary is not merged into a tool group", () => {
  for (const kind of ["pi.compaction", "pi.reset"] as const) {
    const timeline = buildTimeline([
      assistant(1, "Before the boundary.", [
        { id: "call-1", name: "web_search" },
      ]),
      boundary(2, kind),
      toolResult(3, "call-1"),
    ]);

    expect(timeline.map((item) => item.kind)).toEqual([
      "assistant",
      "entry",
      "entry",
    ]);
    const step = timeline[0];
    expect(step.kind).toBe("assistant");
    if (step.kind !== "assistant") {
      continue;
    }
    expect(step.results).toHaveLength(0);
    expect(timeline[1].entry.kind).toBe(kind);
    expect(timeline[2].entry.id).toBe(3);
  }
});

test("empty assistant steps do not produce empty bubbles", () => {
  const timeline = buildTimeline([
    assistant(1, "   "),
    assistant(2, "A real answer."),
  ]);

  expect(timeline).toHaveLength(1);
  const step = timeline[0];
  expect(step.kind).toBe("assistant");
  if (step.kind !== "assistant") {
    return;
  }
  expect(step.entry.id).toBe(2);
  expect(step.step).toBe(2);
});
