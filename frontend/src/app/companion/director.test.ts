// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { actionForTool } from "./actions";
import {
  AGENT_OVERRIDE_MS,
  MIN_DWELL_MS,
  SLEEP_AFTER_MS,
  advanceDirector,
  agentGestures,
  desiredPose,
  nextSignalChange,
  snapshotStream,
  type CompanionSignals,
  type CompanionStreamInput,
  type CompanionStreamTool,
} from "./director";

const NOW = 1_000_000;

function signals(patch: Partial<CompanionSignals> = {}): CompanionSignals {
  return {
    now: NOW,
    held: false,
    stream: null,
    override: null,
    greetUntil: 0,
    successUntil: 0,
    confusedUntil: 0,
    listeningUntil: 0,
    lastActivityAt: NOW,
    ...patch,
  };
}

function tool(
  name: string,
  status = "running",
  args: Record<string, unknown> | null = null,
  id = name,
): CompanionStreamTool {
  return { id, name, status, arguments: args };
}

function stream(patch: Partial<CompanionStreamInput> = {}): CompanionStreamInput {
  return { status: "running", segments: [], toolCalls: [], error: null, ...patch };
}

describe("tool mapping", () => {
  test("maps archive tools to poses", () => {
    expect(actionForTool("search_knowledge")).toBe("searching");
    expect(actionForTool("read_file")).toBe("reading");
    expect(actionForTool("history_message")).toBe("reading");
    expect(actionForTool("save_memory")).toBe("writing");
    expect(actionForTool("render_plot")).toBe("calculating");
    expect(actionForTool("web_fetch")).toBe("browsing");
    expect(actionForTool("present_resource")).toBe("presenting");
    expect(actionForTool("read_something_new")).toBe("reading");
    expect(actionForTool("unknown")).toBeNull();
  });
});

describe("snapshotStream", () => {
  test("null stream stays null", () => {
    expect(snapshotStream(null)).toBeNull();
  });

  test("newest running tool wins and companion tool is ignored", () => {
    const snapshot = snapshotStream(
      stream({
        toolCalls: [
          tool("read_file", "ok"),
          tool("search_knowledge"),
          tool("companion_action", "running", { action: "greet" }),
        ],
      }),
    );
    expect(snapshot?.toolAction).toBe("searching");
  });

  test("unknown running tool still reads as thinking", () => {
    expect(snapshotStream(stream({ toolCalls: [tool("mystery")] }))?.toolAction).toBe(
      "thinking",
    );
  });

  test("speaking only while the last step has prose and no tools", () => {
    const speaking = snapshotStream(
      stream({ segments: [{ text: "Hello", reasoning: "", toolCalls: [] }] }),
    );
    expect(speaking?.speaking).toBe(true);
    const between = snapshotStream(
      stream({
        segments: [{ text: "Let me look", reasoning: "", toolCalls: [tool("read_file", "ok")] }],
      }),
    );
    expect(between?.speaking).toBe(false);
  });
});

describe("agentGestures", () => {
  test("keeps valid companion_action calls only", () => {
    const gestures = agentGestures(
      stream({
        toolCalls: [
          tool("companion_action", "ok", { action: "greet" }, "a"),
          tool("companion_action", "ok", { action: "dance" }, "b"),
          tool("companion_action", "ok", { action: "held" }, "c"),
          tool("read_file", "ok", { action: "success" }, "d"),
        ],
      }),
    );
    expect(gestures).toEqual([{ id: "a", action: "greet" }]);
  });
});

describe("desiredPose", () => {
  test("idle by default, sleeping after the idle window", () => {
    expect(desiredPose(signals()).action).toBe("idle");
    expect(
      desiredPose(signals({ lastActivityAt: NOW - SLEEP_AFTER_MS })).action,
    ).toBe("sleeping");
  });

  test("running stream: thinking, then tool, then speaking", () => {
    expect(
      desiredPose(signals({ stream: { status: "running", toolAction: null, speaking: false } }))
        .action,
    ).toBe("thinking");
    expect(
      desiredPose(
        signals({ stream: { status: "running", toolAction: "searching", speaking: true } }),
      ).action,
    ).toBe("searching");
    expect(
      desiredPose(signals({ stream: { status: "running", toolAction: null, speaking: true } }))
        .action,
    ).toBe("speaking");
  });

  test("never sleeps during a run", () => {
    expect(
      desiredPose(
        signals({
          lastActivityAt: NOW - SLEEP_AFTER_MS * 2,
          stream: { status: "running", toolAction: null, speaking: false },
        }),
      ).action,
    ).toBe("thinking");
  });

  test("approval waiting and failure outrank tools; held outranks everything", () => {
    expect(
      desiredPose(signals({ stream: { status: "waiting", toolAction: null, speaking: false } }))
        .action,
    ).toBe("waiting");
    expect(
      desiredPose(
        signals({
          confusedUntil: NOW + 1,
          stream: { status: "running", toolAction: "reading", speaking: false },
        }),
      ).action,
    ).toBe("confused");
    expect(desiredPose(signals({ held: true, confusedUntil: NOW + 1 })).action).toBe("held");
  });

  test("agent override beats automatic tool poses but not approval", () => {
    const override = { action: "greet" as const, until: NOW + AGENT_OVERRIDE_MS };
    expect(
      desiredPose(
        signals({ override, stream: { status: "running", toolAction: "reading", speaking: false } }),
      ).action,
    ).toBe("greet");
    expect(
      desiredPose(
        signals({ override, stream: { status: "waiting", toolAction: null, speaking: false } }),
      ).action,
    ).toBe("waiting");
    expect(desiredPose(signals({ override: { ...override, until: NOW } })).action).toBe("idle");
  });

  test("transients: success over greet over listening", () => {
    expect(
      desiredPose(signals({ successUntil: NOW + 5, greetUntil: NOW + 5, listeningUntil: NOW + 5 }))
        .action,
    ).toBe("success");
    expect(desiredPose(signals({ greetUntil: NOW + 5, listeningUntil: NOW + 5 })).action).toBe(
      "greet",
    );
    expect(desiredPose(signals({ listeningUntil: NOW + 5 })).action).toBe("listening");
  });
});

describe("nextSignalChange", () => {
  test("returns the soonest future expiry", () => {
    expect(nextSignalChange(signals({ greetUntil: NOW + 50, successUntil: NOW + 20 }))).toBe(
      NOW + 20,
    );
    expect(nextSignalChange(signals())).toBe(NOW + SLEEP_AFTER_MS);
  });
});

describe("advanceDirector", () => {
  const start = { action: "idle" as const, since: NOW };

  test("holds a pose for the minimum dwell", () => {
    const step = advanceDirector(start, { action: "searching", priority: 52 }, NOW + 100);
    expect(step.state).toBe(start);
    expect(step.wakeAt).toBe(NOW + MIN_DWELL_MS);
    const later = advanceDirector(start, { action: "searching", priority: 52 }, NOW + MIN_DWELL_MS);
    expect(later.state.action).toBe("searching");
  });

  test("urgent poses and leaving held skip the dwell", () => {
    expect(advanceDirector(start, { action: "held", priority: 100 }, NOW + 1).state.action).toBe(
      "held",
    );
    expect(
      advanceDirector({ action: "held", since: NOW }, { action: "idle", priority: 0 }, NOW + 1)
        .state.action,
    ).toBe("idle");
  });

  test("same action is a no-op", () => {
    expect(advanceDirector(start, { action: "idle", priority: 0 }, NOW + 5)).toEqual({
      state: start,
      wakeAt: null,
    });
  });
});
