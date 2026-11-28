/**
 * Pure companion state machine: chat signals in, one pose out. The hook layer
 * owns clocks and timers; everything here is deterministic for tests.
 */
import { readSurfacedLore } from "./story";
import {
  ACTION_PRIORITY,
  AGENT_OVERRIDE_PRIORITY,
  COMPANION_TOOL_NAME,
  actionForTool,
  isCompanionAction,
  type CompanionAction,
} from "./actions";

/** Minimum time a pose stays on screen before a lower-urgency change. */
export const MIN_DWELL_MS = 900;
/** How long an explicit agent gesture overrides automatic poses. */
export const AGENT_OVERRIDE_MS = 3000;
/** Idle time before the companion dozes off on its strings. */
export const SLEEP_AFTER_MS = 120_000;
export const GREET_MS = 2400;
export const SUCCESS_MS = 2600;
export const CONFUSED_MS = 4200;
export const LISTEN_MS = 3500;

/** Changes at or above this priority skip the dwell (held, failure, approval). */
const URGENT_PRIORITY = 75;

/** The structural slice of a live chat stream the companion reads. */
export interface CompanionStreamTool {
  readonly id: string;
  readonly name: string;
  readonly status: string;
  readonly arguments: Readonly<Record<string, unknown>> | null;
  /** Tool result data; search results may carry surfaced lore. */
  readonly data?: unknown;
}

export interface CompanionStreamSegment {
  readonly text: string;
  readonly reasoning: string;
  readonly toolCalls: readonly CompanionStreamTool[];
}

export interface CompanionStreamInput {
  readonly status: "running" | "waiting" | "done" | "failed";
  readonly segments: readonly CompanionStreamSegment[];
  readonly toolCalls: readonly CompanionStreamTool[];
  readonly error: unknown;
}

export interface StreamSnapshot {
  readonly status: CompanionStreamInput["status"];
  /** Pose for the newest running archive tool, if one is running. */
  readonly toolAction: CompanionAction | null;
  /** True while the newest step is producing visible prose. */
  readonly speaking: boolean;
}

function isRunning(status: string): boolean {
  return status === "running" || status === "pending";
}

/** Reduce a live stream to the three facts the director needs. */
export function snapshotStream(
  stream: CompanionStreamInput | null,
): StreamSnapshot | null {
  if (stream === null) {
    return null;
  }
  let toolAction: CompanionAction | null = null;
  for (let index = stream.toolCalls.length - 1; index >= 0; index -= 1) {
    const tool = stream.toolCalls[index];
    if (tool.name === COMPANION_TOOL_NAME || !isRunning(tool.status)) {
      continue;
    }
    toolAction = actionForTool(tool.name) ?? "thinking";
    break;
  }
  const last = stream.segments.at(-1);
  const speaking =
    last !== undefined && last.text.length > 0 && last.toolCalls.length === 0;
  return { status: stream.status, toolAction, speaking };
}

export interface AgentGesture {
  readonly id: string;
  readonly action: CompanionAction;
}

/** Explicit `companion_action` calls, oldest first, with valid actions only. */
export function agentGestures(
  stream: CompanionStreamInput | null,
): readonly AgentGesture[] {
  if (stream === null) {
    return [];
  }
  const gestures: AgentGesture[] = [];
  for (const tool of stream.toolCalls) {
    if (tool.name !== COMPANION_TOOL_NAME) {
      continue;
    }
    const action = tool.arguments?.action;
    if (isCompanionAction(action) && action !== "held") {
      gestures.push({ id: tool.id, action });
    }
  }
  return gestures;
}

/** How long the companion lingers over its own surfaced memory. */
export const LORE_POSE_MS = 2500;

/**
 * Finished search steps that surfaced the librarian's own memories. Each one
 * earns a brief, soft "reading" pose (once per tool call).
 */
export function loreMoments(stream: CompanionStreamInput | null): readonly string[] {
  if (stream === null) {
    return [];
  }
  return stream.toolCalls
    .filter(
      (tool) =>
        tool.name === "search_knowledge" &&
        !isRunning(tool.status) &&
        readSurfacedLore(tool.data).length > 0,
    )
    .map((tool) => `lore:${tool.id}`);
}

export interface CompanionSignals {
  readonly now: number;
  readonly held: boolean;
  readonly stream: StreamSnapshot | null;
  readonly override: { readonly action: CompanionAction; readonly until: number } | null;
  readonly greetUntil: number;
  readonly successUntil: number;
  readonly confusedUntil: number;
  readonly listeningUntil: number;
  readonly lastActivityAt: number;
}

export interface DesiredPose {
  readonly action: CompanionAction;
  readonly priority: number;
}

/** Pick the highest-priority pose the current signals ask for. */
export function desiredPose(signals: CompanionSignals): DesiredPose {
  const { now } = signals;
  const candidates: DesiredPose[] = [];
  const offer = (action: CompanionAction, priority = ACTION_PRIORITY[action]) =>
    candidates.push({ action, priority });

  if (signals.held) {
    offer("held");
  }
  if (signals.confusedUntil > now) {
    offer("confused");
  }
  if (signals.override !== null && signals.override.until > now) {
    offer(signals.override.action, AGENT_OVERRIDE_PRIORITY);
  }
  const stream = signals.stream;
  if (stream !== null) {
    if (stream.status === "waiting") {
      offer("waiting");
    } else if (stream.status === "running") {
      if (stream.toolAction !== null) {
        offer(stream.toolAction);
      } else if (stream.speaking) {
        offer("speaking");
      } else {
        offer("thinking");
      }
    }
  }
  if (signals.successUntil > now) {
    offer("success");
  }
  if (signals.greetUntil > now) {
    offer("greet");
  }
  if (signals.listeningUntil > now) {
    offer("listening");
  }
  const busy = stream !== null && stream.status !== "done" && stream.status !== "failed";
  if (!busy && !signals.held && now - signals.lastActivityAt >= SLEEP_AFTER_MS) {
    offer("sleeping");
  }
  offer("idle");

  return candidates.reduce<DesiredPose>(
    (best, item) => (item.priority > best.priority ? item : best),
    { action: "idle", priority: Number.NEGATIVE_INFINITY },
  );
}

/** The next moment a time-based signal expires, for the hook's timer. */
export function nextSignalChange(signals: CompanionSignals): number | null {
  const { now } = signals;
  const moments = [
    signals.override?.until ?? 0,
    signals.greetUntil,
    signals.successUntil,
    signals.confusedUntil,
    signals.listeningUntil,
    signals.lastActivityAt + SLEEP_AFTER_MS,
  ].filter((moment) => moment > now);
  return moments.length > 0 ? Math.min(...moments) : null;
}

export interface DirectorState {
  readonly action: CompanionAction;
  readonly since: number;
}

export interface DirectorStep {
  readonly state: DirectorState;
  /** When a pending lower-urgency change may happen, or null. */
  readonly wakeAt: number | null;
}

/**
 * Advance the displayed pose toward the desired one. Urgent changes apply at
 * once; others wait out the minimum dwell so tool bursts never flicker.
 */
export function advanceDirector(
  state: DirectorState,
  desired: DesiredPose,
  now: number,
  dwellMs: number = MIN_DWELL_MS,
): DirectorStep {
  if (desired.action === state.action) {
    return { state, wakeAt: null };
  }
  const urgent = desired.priority >= URGENT_PRIORITY;
  const leavingHeld = state.action === "held";
  if (urgent || leavingHeld || now - state.since >= dwellMs) {
    return { state: { action: desired.action, since: now }, wakeAt: null };
  }
  return { state, wakeAt: state.since + dwellMs };
}
