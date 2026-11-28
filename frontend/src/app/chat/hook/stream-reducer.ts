/**
 * Pure reducer for one live agent turn. The hook owns transport and React
 * state; everything here is deterministic so it can be tested with bun:test.
 */
import type { AgentStreamEvent } from "../../../apis/agent-stream";
import { appendReasoningDelta } from "./reasoning-stream";
import {
  readResource,
  type ChatAttachmentView,
  type JsonRecord,
  type ResourceMeta,
} from "../types";

export interface ChatStreamTool {
  readonly id: string;
  readonly name: string;
  readonly arguments: JsonRecord | null;
  readonly status: string;
  readonly resource: ResourceMeta | null;
  readonly entryId: number | null;
  readonly data: JsonRecord | null;
  readonly durationMs: number | null;
  readonly errorCode: string | null;
}

/** One assistant step and the tool calls made after its prose. */
export interface ChatStreamSegment {
  /** 1-based step number within this turn. */
  readonly index: number;
  readonly text: string;
  readonly toolCalls: readonly ChatStreamTool[];
  /** Provider reasoning streamed before this step's visible text. */
  readonly reasoning: string;
  /** Provider-reported reasoning tokens for this step, when available. */
  readonly reasoningTokens: number;
}

export interface ChatStreamView {
  readonly conversationId: number;
  readonly userContent: string;
  readonly userAttachments: readonly ChatAttachmentView[];
  /** The ordered segment history; earlier prose is never discarded. */
  readonly segments: readonly ChatStreamSegment[];
  /** Aggregate prose kept for the inspector. */
  readonly assistantText: string;
  /** Flat tool list kept for the inspector and memory-title lookup. */
  readonly toolCalls: readonly ChatStreamTool[];
  readonly usage: Readonly<Record<string, number>>;
  readonly finishReason: string | null;
  readonly error: { readonly code: string; readonly detail: string } | null;
  readonly runId: number | null;
  readonly pageContextEntryId: number | null;
  readonly pageContextAttached: boolean;
  readonly pageContextKey: string | null;
  readonly status: "running" | "waiting" | "done" | "failed";
}

function upsertTool(
  tools: readonly ChatStreamTool[],
  callId: string,
  patch: Partial<ChatStreamTool> & { readonly name: string },
): ChatStreamTool[] {
  const index = tools.findIndex((tool) => tool.id === callId);
  if (index < 0) {
    return [
      ...tools,
      {
        id: callId,
        name: patch.name,
        arguments: patch.arguments ?? null,
        status: patch.status ?? "running",
        resource: patch.resource ?? null,
        entryId: patch.entryId ?? null,
        data: patch.data ?? null,
        durationMs: patch.durationMs ?? null,
        errorCode: patch.errorCode ?? null,
      },
    ];
  }
  return tools.map((tool, toolIndex) =>
    toolIndex === index ? { ...tool, ...patch, id: callId } : tool,
  );
}

function segmentsText(segments: readonly ChatStreamSegment[]): string {
  return segments
    .map((segment) => segment.text)
    .filter((text) => text.length > 0)
    .join("\n\n");
}

/** Keep the aggregate fields and the ordered segments in one assignment. */
function withSegments(
  state: ChatStreamView,
  segments: readonly ChatStreamSegment[],
): ChatStreamView {
  return { ...state, segments, assistantText: segmentsText(segments) };
}

function ensureSegments(
  segments: readonly ChatStreamSegment[],
): ChatStreamSegment[] {
  return segments.length > 0
    ? [...segments]
    : [
        {
          index: 1,
          text: "",
          toolCalls: [],
          reasoning: "",
          reasoningTokens: 0,
        },
      ];
}

function updateLastSegment(
  segments: readonly ChatStreamSegment[],
  update: (segment: ChatStreamSegment) => ChatStreamSegment,
): ChatStreamSegment[] {
  const base = ensureSegments(segments);
  const lastIndex = base.length - 1;
  return base.map((segment, index) =>
    index === lastIndex ? update(segment) : segment,
  );
}

function updateSegmentTool(
  segments: readonly ChatStreamSegment[],
  callId: string,
  patch: Partial<ChatStreamTool> & { readonly name: string },
): ChatStreamSegment[] {
  const base = ensureSegments(segments);
  let target = base.findIndex((segment) =>
    segment.toolCalls.some((tool) => tool.id === callId),
  );
  if (target < 0) {
    target = base.length - 1;
  }
  return base.map((segment, index) =>
    index === target
      ? {
          ...segment,
          toolCalls: upsertTool(segment.toolCalls, callId, patch),
        }
      : segment,
  );
}

function startAssistantSegment(state: ChatStreamView): ChatStreamView {
  const segments = [...state.segments];
  const current = segments.at(-1);
  const fresh =
    current === undefined ||
    current.text.length > 0 ||
    current.toolCalls.length > 0 ||
    current.reasoning.length > 0;
  if (fresh) {
    segments.push({
      index: segments.length + 1,
      text: "",
      toolCalls: [],
      reasoning: "",
      reasoningTokens: 0,
    });
  }
  return {
    ...withSegments(state, segments),
    finishReason: fresh ? null : state.finishReason,
    usage: fresh ? {} : state.usage,
    status: "running",
  };
}

export function applyStreamEvent(
  state: ChatStreamView,
  event: AgentStreamEvent,
): ChatStreamView {
  switch (event.type) {
    case "run_start":
      return {
        ...state,
        runId: event.data.run_id,
        pageContextEntryId: event.data.page_context_entry_id,
        pageContextAttached: event.data.page_context_attached,
      };
    case "message_start":
      return startAssistantSegment(state);
    case "message_delta": {
      const segments = updateLastSegment(state.segments, (segment) => ({
        ...segment,
        text: segment.text + event.data.delta,
      }));
      return withSegments(state, segments);
    }
    case "reasoning_delta":
      return withSegments(
        state,
        appendReasoningDelta(state.segments, event.data.delta),
      );
    case "message_end": {
      const reasoningTokens = event.data.usage.reasoning_tokens ?? 0;
      const segments =
        reasoningTokens > 0
          ? updateLastSegment(state.segments, (segment) => ({
              ...segment,
              reasoningTokens,
            }))
          : state.segments;
      return {
        ...withSegments(state, segments),
        usage: event.data.usage,
        finishReason: event.data.finish_reason,
      };
    }
    case "tool_start": {
      const patch = {
        name: event.data.name,
        arguments: event.data.arguments,
        status: "running",
        entryId: event.data.entry_id,
      } as const;
      return {
        ...withSegments(
          state,
          updateSegmentTool(state.segments, event.data.tool_call_id, patch),
        ),
        toolCalls: upsertTool(state.toolCalls, event.data.tool_call_id, patch),
      };
    }
    case "tool_end": {
      const patch = {
        name: event.data.name,
        status: event.data.status,
        resource: readResource(event.data.resource),
        entryId: event.data.entry_id,
        data: event.data.data,
        durationMs: event.data.duration_ms,
        errorCode: event.data.error_code,
      };
      return {
        ...withSegments(
          state,
          updateSegmentTool(state.segments, event.data.tool_call_id, patch),
        ),
        toolCalls: upsertTool(state.toolCalls, event.data.tool_call_id, patch),
      };
    }
    case "approval_required":
      return { ...state, status: "waiting" };
    case "run_end": {
      const status = event.data.status;
      let mapped: ChatStreamView["status"] = "failed";
      if (status === "completed" || status === "cancelled") {
        mapped = "done";
      } else if (status === "waiting") {
        mapped = "waiting";
      }
      return { ...state, status: mapped };
    }
    case "error":
      return { ...state, error: event.data, status: "failed" };
    default:
      return state;
  }
}

/** Seed state for a turn before the first server event arrives. */
export function createStreamView(
  conversationId: number,
  userContent: string,
  userAttachments: readonly ChatAttachmentView[],
  pageContextKey: string | null,
): ChatStreamView {
  return {
    conversationId,
    userContent,
    userAttachments,
    segments: [],
    assistantText: "",
    toolCalls: [],
    usage: {},
    finishReason: null,
    error: null,
    runId: null,
    pageContextEntryId: null,
    pageContextAttached: false,
    pageContextKey,
    status: "running",
  };
}

/** Token-sized events that may be buffered until the next animation frame. */
export function isDeltaEvent(event: AgentStreamEvent): boolean {
  return event.type === "message_delta" || event.type === "reasoning_delta";
}

/**
 * Merge adjacent deltas of the same kind so a frame's worth of tokens costs
 * one state transition. Order across kinds is preserved exactly.
 */
export function coalesceDeltas(
  events: readonly AgentStreamEvent[],
): AgentStreamEvent[] {
  const merged: AgentStreamEvent[] = [];
  for (const event of events) {
    const previous = merged.at(-1);
    if (previous?.type === "message_delta" && event.type === "message_delta") {
      merged[merged.length - 1] = {
        ...previous,
        data: { ...previous.data, delta: previous.data.delta + event.data.delta },
      };
      continue;
    }
    if (
      previous?.type === "reasoning_delta" &&
      event.type === "reasoning_delta"
    ) {
      merged[merged.length - 1] = {
        ...previous,
        data: { ...previous.data, delta: previous.data.delta + event.data.delta },
      };
      continue;
    }
    merged.push(event);
  }
  return merged;
}

/** Apply a batch of events in order. */
export function applyStreamEvents(
  state: ChatStreamView,
  events: readonly AgentStreamEvent[],
): ChatStreamView {
  return coalesceDeltas(events).reduce(applyStreamEvent, state);
}
