// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  AGENT_OVERRIDE_MS,
  GREET_MS,
  MIN_DWELL_MS,
  SLEEP_AFTER_MS,
  type CompanionStreamInput,
} from "./director";
import { CompanionDirectorEngine, type EngineClock } from "./director-engine";

class FakeClock implements EngineClock {
  time = 10_000;
  private timers: { at: number; callback: () => void; id: number }[] = [];
  private nextId = 1;

  readonly now = () => this.time;

  readonly setTimer = (callback: () => void, ms: number) => {
    const id = this.nextId++;
    this.timers.push({ at: this.time + ms, callback, id });
    return id;
  };

  readonly clearTimer = (handle: unknown) => {
    this.timers = this.timers.filter((timer) => timer.id !== handle);
  };

  advance(ms: number): void {
    const end = this.time + ms;
    for (;;) {
      const due = this.timers
        .filter((timer) => timer.at <= end)
        .sort((a, b) => a.at - b.at)[0];
      if (due === undefined) {
        break;
      }
      this.timers = this.timers.filter((timer) => timer !== due);
      this.time = due.at;
      due.callback();
    }
    this.time = end;
  }
}

function running(patch: Partial<CompanionStreamInput> = {}): CompanionStreamInput {
  return { status: "running", segments: [], toolCalls: [], error: null, ...patch };
}

describe("CompanionDirectorEngine", () => {
  test("greets a new conversation, then settles to idle and sleeps", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.noteConversation("new");
    expect(engine.getSnapshot()).toBe("greet");
    clock.advance(GREET_MS + MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("idle");
    clock.advance(SLEEP_AFTER_MS);
    expect(engine.getSnapshot()).toBe("sleeping");
    engine.poke();
    clock.advance(MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("idle");
  });

  test("tool bursts respect dwell, then success after the run", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.noteConversation("1");
    clock.advance(MIN_DWELL_MS);
    engine.noteStream(running());
    clock.advance(MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("thinking");
    engine.noteStream(
      running({ toolCalls: [{ id: "t", name: "search_knowledge", status: "running", arguments: null }] }),
    );
    clock.advance(10);
    expect(engine.getSnapshot()).toBe("searching");
    engine.noteStream(
      running({ toolCalls: [{ id: "t", name: "read_file", status: "running", arguments: null }] }),
    );
    clock.advance(100);
    expect(engine.getSnapshot()).toBe("searching");
    clock.advance(MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("reading");
    engine.noteStream({ ...running(), status: "done" });
    clock.advance(MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("success");
    engine.dispose();
  });

  test("agent gesture overrides for a few seconds, failure is immediate", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.noteConversation("1");
    clock.advance(MIN_DWELL_MS);
    engine.noteStream(
      running({
        toolCalls: [{ id: "g", name: "companion_action", status: "ok", arguments: { action: "presenting" } }],
      }),
    );
    expect(engine.getSnapshot()).toBe("presenting");
    clock.advance(AGENT_OVERRIDE_MS + MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("thinking");
    engine.noteStream({ ...running(), status: "failed" });
    expect(engine.getSnapshot()).toBe("confused");
  });

  test("held is immediate and releases at once", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.setHeld(true);
    expect(engine.getSnapshot()).toBe("held");
    engine.setHeld(false);
    expect(engine.getSnapshot()).toBe("idle");
  });

  test("surfaced lore earns a brief reading pose once", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.noteConversation("1");
    clock.advance(MIN_DWELL_MS);
    const search = {
      id: "s",
      name: "search_knowledge",
      status: "ok",
      arguments: null,
      data: { lore: [{ id: 1, text: "I kept the ledgers once." }] },
    };
    engine.noteStream(running({ toolCalls: [search] }));
    expect(engine.getSnapshot()).toBe("reading");
    clock.advance(AGENT_OVERRIDE_MS + MIN_DWELL_MS);
    expect(engine.getSnapshot()).toBe("thinking");
    engine.noteStream(running({ toolCalls: [search] }));
    clock.advance(10);
    expect(engine.getSnapshot()).toBe("thinking");
  });

  test("typing listens", () => {
    const clock = new FakeClock();
    const engine = new CompanionDirectorEngine(clock);
    engine.noteConversation("1");
    clock.advance(MIN_DWELL_MS);
    engine.noteDraft("hel");
    expect(engine.getSnapshot()).toBe("listening");
  });
});
