/**
 * Clocked wrapper around the pure director. React feeds it observations
 * (stream changes, typing, conversation switches, drags) and reads the
 * displayed pose through `useSyncExternalStore`; timers live here, not in
 * render.
 */
import type { CompanionAction } from "./actions";
import {
  AGENT_OVERRIDE_MS,
  CONFUSED_MS,
  GREET_MS,
  LISTEN_MS,
  LORE_POSE_MS,
  MIN_DWELL_MS,
  SUCCESS_MS,
  advanceDirector,
  agentGestures,
  desiredPose,
  loreMoments,
  nextSignalChange,
  snapshotStream,
  type CompanionSignals,
  type CompanionStreamInput,
  type DirectorState,
} from "./director";

export interface EngineClock {
  readonly now: () => number;
  readonly setTimer: (callback: () => void, ms: number) => unknown;
  readonly clearTimer: (handle: unknown) => void;
}

const browserClock: EngineClock = {
  now: () => Date.now(),
  setTimer: (callback, ms) => window.setTimeout(callback, ms),
  clearTimer: (handle) => window.clearTimeout(handle as number),
};

type Listener = () => void;

export class CompanionDirectorEngine {
  private readonly clock: EngineClock;
  private readonly listeners = new Set<Listener>();
  private state: DirectorState;
  private timer: unknown = null;
  private held = false;
  private stream: CompanionStreamInput | null = null;
  private lastStatus: CompanionStreamInput["status"] | null = null;
  private readonly seenGestures = new Set<string>();
  private override: CompanionSignals["override"] = null;
  private greetUntil = 0;
  private successUntil = 0;
  private confusedUntil = 0;
  private listeningUntil = 0;
  private lastActivityAt: number;
  private conversationKey: string | null = null;
  private lastDraft = "";

  constructor(clock: EngineClock = browserClock) {
    this.clock = clock;
    const now = clock.now();
    this.lastActivityAt = now;
    // Start "settled" so the first real signal shows without waiting.
    this.state = { action: "idle", since: now - MIN_DWELL_MS };
  }

  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getSnapshot = (): CompanionAction => this.state.action;

  /** A new or switched conversation greets the reader once. */
  noteConversation(key: string): void {
    if (key === this.conversationKey) {
      return;
    }
    const first = this.conversationKey === null;
    this.conversationKey = key;
    this.seenGestures.clear();
    this.override = null;
    const now = this.touch();
    if (!first || key === "new") {
      this.greetUntil = now + GREET_MS;
    }
    this.evaluate();
  }

  /** Typing in the composer makes the companion lean in and listen. */
  noteDraft(draft: string): void {
    if (draft === this.lastDraft) {
      return;
    }
    this.lastDraft = draft;
    const now = this.touch();
    this.listeningUntil = draft.trim().length > 0 ? now + LISTEN_MS : 0;
    this.evaluate();
  }

  noteStream(stream: CompanionStreamInput | null): void {
    if (stream === this.stream) {
      return;
    }
    this.stream = stream;
    const now = this.touch();
    for (const gesture of agentGestures(stream)) {
      if (!this.seenGestures.has(gesture.id)) {
        this.seenGestures.add(gesture.id);
        this.override = { action: gesture.action, until: now + AGENT_OVERRIDE_MS };
      }
    }
    for (const moment of loreMoments(stream)) {
      if (!this.seenGestures.has(moment)) {
        this.seenGestures.add(moment);
        // An explicit agent gesture already playing keeps the stage.
        if (this.override === null || this.override.until <= now) {
          this.override = { action: "reading", until: now + LORE_POSE_MS };
        }
      }
    }
    const status = stream?.status ?? null;
    if (status !== this.lastStatus) {
      if (status === "done") {
        this.successUntil = now + SUCCESS_MS;
      } else if (status === "failed") {
        this.confusedUntil = now + CONFUSED_MS;
      } else if (status === "running" && this.lastStatus === null) {
        this.listeningUntil = 0;
        this.greetUntil = 0;
      }
      this.lastStatus = status;
    }
    this.evaluate();
  }

  setHeld(held: boolean): void {
    if (held === this.held) {
      return;
    }
    this.held = held;
    this.touch();
    this.evaluate();
  }

  /** Any explicit interaction (tap, keyboard move) wakes a sleeping figure. */
  poke(): void {
    this.touch();
    this.evaluate();
  }

  dispose(): void {
    if (this.timer !== null) {
      this.clock.clearTimer(this.timer);
      this.timer = null;
    }
  }

  private touch(): number {
    const now = this.clock.now();
    this.lastActivityAt = now;
    return now;
  }

  private signals(now: number): CompanionSignals {
    return {
      now,
      held: this.held,
      stream: snapshotStream(this.stream),
      override: this.override,
      greetUntil: this.greetUntil,
      successUntil: this.successUntil,
      confusedUntil: this.confusedUntil,
      listeningUntil: this.listeningUntil,
      lastActivityAt: this.lastActivityAt,
    };
  }

  private evaluate = (): void => {
    if (this.timer !== null) {
      this.clock.clearTimer(this.timer);
      this.timer = null;
    }
    const now = this.clock.now();
    const signals = this.signals(now);
    const step = advanceDirector(this.state, desiredPose(signals), now);
    if (step.state !== this.state) {
      this.state = step.state;
      for (const listener of this.listeners) {
        listener();
      }
    }
    const moments = [step.wakeAt, nextSignalChange(signals)].filter(
      (moment): moment is number => moment !== null && moment > now,
    );
    if (moments.length > 0) {
      const delay = Math.max(16, Math.min(...moments) - now + 1);
      this.timer = this.clock.setTimer(this.evaluate, delay);
    }
  };
}
