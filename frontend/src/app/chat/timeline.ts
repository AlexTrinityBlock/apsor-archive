/**
 * The reading order of one persisted agent turn.
 *
 * The transcript stores every provider step as its own assistant entry and
 * every tool call as its own tool-result entry. This module groups one
 * assistant step with the tool results that immediately follow it, so the
 * renderer can keep "prose, tool, prose, tool" in exactly the recorded order.
 *
 * Nothing here changes an entry or reads hidden reasoning; it only describes
 * which entries belong together.
 */
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import {
  assistantText,
  readAssistantMeta,
  readToolCalls,
  readToolResultInfo,
  type ToolCallMeta,
  type ToolResultInfo,
} from "./types";

export interface TimelineToolResult {
  readonly entry: AgentEntrySchema;
  readonly info: ToolResultInfo;
  /** The matching call in the assistant step, or null for an orphan result. */
  readonly call: ToolCallMeta | null;
}

export interface TimelineAssistantStep {
  readonly kind: "assistant";
  readonly entry: AgentEntrySchema;
  readonly text: string;
  /** `data.step` when recorded, otherwise the ordinal assistant step. */
  readonly step: number | null;
  readonly calls: readonly ToolCallMeta[];
  /** Every tool result immediately after this step, in transcript order. */
  readonly results: readonly TimelineToolResult[];
}

export interface TimelineEntry {
  readonly kind: "entry";
  readonly entry: AgentEntrySchema;
}

export type TimelineItem = TimelineAssistantStep | TimelineEntry;

function isEmptyStep(
  text: string,
  calls: readonly ToolCallMeta[],
  results: readonly TimelineToolResult[],
  hasError: boolean,
): boolean {
  return (
    text.trim().length === 0 &&
    calls.length === 0 &&
    results.length === 0 &&
    !hasError
  );
}

/**
 * Group assistant entries with their immediately following tool results.
 *
 * A boundary (user, compaction, reset, page context, notice, or an unexpected
 * kind) ends the group. Tool results that are not adjacent to an assistant
 * step stay in the timeline as their own entries, so an orphan or a result
 * separated by a boundary is never dropped. A step with no prose, no call, and
 * no result is omitted rather than rendered as an empty bubble.
 */
export function buildTimeline(
  entries: readonly AgentEntrySchema[],
): TimelineItem[] {
  const items: TimelineItem[] = [];
  let assistantOrdinal = 0;
  let index = 0;

  while (index < entries.length) {
    const entry = entries[index];
    if (entry.kind !== "pi.assistant") {
      items.push({ kind: "entry", entry });
      index += 1;
      continue;
    }

    assistantOrdinal += 1;
    const meta = readAssistantMeta(entry);
    const text = assistantText(entry);
    const calls = readToolCalls(entry);
    const results: TimelineToolResult[] = [];
    let next = index + 1;
    while (next < entries.length && entries[next].kind === "pi.tool-result") {
      const info = readToolResultInfo(entries[next]);
      const call =
        calls.find((candidate) => candidate.id === info.callId) ?? null;
      results.push({ entry: entries[next], info, call });
      next += 1;
    }

    if (!isEmptyStep(text, calls, results, meta.error !== null)) {
      items.push({
        kind: "assistant",
        entry,
        text,
        step: meta.step ?? assistantOrdinal,
        calls,
        results,
      });
    }
    index = next;
  }

  return items;
}
