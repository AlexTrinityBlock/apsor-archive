import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { isRecord, numberValue, stringValue } from "./types";

/**
 * Collect memory ids and titles from persisted tool results and the live
 * stream. Tool payloads carry `memory_id` + `title` in several shapes
 * (read_memory previews, search hits, save receipts), so one bounded walk is
 * less brittle than enumerating every tool's data schema.
 */
function walk(value: unknown, out: Map<number, string>, depth: number): void {
  if (depth > 8) {
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      walk(item, out, depth + 1);
    }
    return;
  }
  if (!isRecord(value)) {
    return;
  }

  const memoryId =
    numberValue(value.memory_id) ??
    (value.resource_type === "memory"
      ? numberValue(value.resource_id)
      : null);
  const title = stringValue(value.title);
  if (memoryId !== null && title) {
    out.set(memoryId, title);
  }

  for (const child of Object.values(value)) {
    walk(child, out, depth + 1);
  }
}

export function buildMemoryTitles(
  entries: readonly AgentEntrySchema[],
  liveToolData: readonly unknown[] = [],
): ReadonlyMap<number, string> {
  const titles = new Map<number, string>();
  for (const entry of entries) {
    if (entry.kind === "pi.tool-result") {
      walk(entry.data, titles, 0);
    }
  }
  for (const data of liveToolData) {
    walk(data, titles, 0);
  }
  return titles;
}

/** The visible citation suffix; the id stays the primary label. */
export function memoryTitleFor(
  memoryId: number,
  titles: ReadonlyMap<number, string>,
): string | null {
  return titles.get(memoryId) ?? null;
}
