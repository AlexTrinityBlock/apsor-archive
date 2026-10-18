import type { MemorySchema, SummarySchema } from "../../generated-apis-types/schemas";

export interface MemorySaveReceipt {
  readonly deprecated: MemorySchema[];
  readonly summary: SummarySchema | null;
}

interface UnknownRecord {
  readonly [key: string]: unknown;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null;
}

function isMemorySchema(value: unknown): value is MemorySchema {
  return (
    isRecord(value) &&
    typeof value.memory_id === "number" &&
    typeof value.content === "string" &&
    (value.status === "active" || value.status === "deprecated") &&
    typeof value.update_time === "string" &&
    Array.isArray(value.supersedes_ids) &&
    value.supersedes_ids.every((id) => typeof id === "number") &&
    (value.superseded_by_id === null || typeof value.superseded_by_id === "number") &&
    typeof value.source === "string" &&
    typeof value.created_at === "string" &&
    (value.deleted_at === null || typeof value.deleted_at === "string")
  );
}

function isSummarySchema(value: unknown): value is SummarySchema {
  return (
    isRecord(value) &&
    typeof value.memory_summary_id === "number" &&
    typeof value.content === "string" &&
    typeof value.period_start === "string" &&
    typeof value.period_end === "string" &&
    typeof value.memory_count === "number" &&
    Array.isArray(value.source_memory_ids) &&
    value.source_memory_ids.every((id) => typeof id === "number") &&
    Array.isArray(value.themes) &&
    value.themes.every((theme) => typeof theme === "string") &&
    (value.generator === "deepseek" || value.generator === "extractive") &&
    (value.model === null || typeof value.model === "string") &&
    typeof value.created_at === "string"
  );
}

/** Recovers the save receipt handed over by the composer after navigation. */
export function parseMemorySaveReceipt(state: unknown): MemorySaveReceipt | null {
  if (!isRecord(state) || !Array.isArray(state.deprecated)) {
    return null;
  }
  return {
    deprecated: state.deprecated.filter(isMemorySchema),
    summary: isSummarySchema(state.summary) ? state.summary : null,
  };
}

export function parseMemoryId(raw: string | undefined): number | null {
  if (!raw || !/^\d+$/.test(raw)) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function nowLocalInput(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export interface ParsedSupersedes {
  readonly ids: number[];
  readonly error: string | null;
}

/** Parses the comma-separated supersede field while preserving first-seen order. */
export function parseSupersedes(raw: string): ParsedSupersedes {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return { ids: [], error: null };
  }
  const seen = new Set<number>();
  for (const token of trimmed.split(/[\s,]+/).filter(Boolean)) {
    if (!/^\d+$/.test(token)) {
      return { ids: [], error: "Use comma-separated numeric memory ids, for example 12, 14." };
    }
    const id = Number(token);
    if (!Number.isSafeInteger(id) || id < 1) {
      return { ids: [], error: "Memory ids must be positive integers." };
    }
    seen.add(id);
  }
  if (seen.size > 50) {
    return { ids: [], error: "A memory can supersede at most 50 earlier memories." };
  }
  return { ids: [...seen], error: null };
}

export function errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return "The archive did not answer.";
}

export function savedMemoryMessage(memoryId: number, deprecatedCount: number): string {
  if (deprecatedCount === 0) {
    return `Memory ${memoryId} saved.`;
  }
  const noun = deprecatedCount === 1 ? "earlier memory is" : "earlier memories are";
  return `Memory ${memoryId} saved; ${deprecatedCount} ${noun} now deprecated.`;
}
