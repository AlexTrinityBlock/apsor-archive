import type { QueryClient } from "@tanstack/react-query";

import type { Translate } from "../../i18n";
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
export function parseSupersedes(raw: string, t: Translate): ParsedSupersedes {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return { ids: [], error: null };
  }
  const seen = new Set<number>();
  for (const token of trimmed.split(/[\s,]+/).filter(Boolean)) {
    if (!/^\d+$/.test(token)) {
      return {
        ids: [],
        error: t("memory.newView.supersedesInvalidFormat"),
      };
    }
    const id = Number(token);
    if (!Number.isSafeInteger(id) || id < 1) {
      return { ids: [], error: t("memory.newView.supersedesPositive") };
    }
    seen.add(id);
  }
  if (seen.size > 50) {
    return { ids: [], error: t("memory.newView.supersedesLimit") };
  }
  return { ids: [...seen], error: null };
}

export function savedMemoryMessage(
  t: Translate,
  memoryId: number,
  deprecatedCount: number,
): string {
  if (deprecatedCount === 0) {
    return t("memory.newView.savedToast", { id: memoryId });
  }
  if (deprecatedCount === 1) {
    return t("memory.newView.savedToastWithDeprecatedOne", { id: memoryId });
  }
  return t("memory.newView.savedToastWithDeprecatedOther", {
    id: memoryId,
    count: deprecatedCount,
  });
}

export interface MemoryPreview {
  readonly thesis: string;
  readonly body: string;
}

function clipAtWord(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  const cut = value.slice(0, Math.max(1, maxLength - 1));
  const lastSpace = cut.lastIndexOf(" ");
  const boundary = lastSpace > maxLength * 0.6 ? cut.slice(0, lastSpace) : cut;
  return `${boundary.trimEnd()}\u2026`;
}

/**
 * Builds a card thesis from the first sentence, falling back to a word-safe
 * character cut. Memory content has no separate title field, so this is a
 * presentation-only split of real text rather than invented metadata.
 */
export function splitMemoryPreview(
  content: string,
  untitledLabel: string,
): MemoryPreview {
  const compact = content.replace(/\s+/g, " ").trim();
  if (compact.length === 0) {
    return { thesis: untitledLabel, body: "" };
  }
  const firstSentence = compact
    .match(/^.{16,320}?[.!?](?=(?:\s+[A-Z0-9"“(]|$))/)?.[0]
    ?.trim();
  if (firstSentence) {
    const remainder = compact.slice(firstSentence.length).trim();
    return {
      thesis: firstSentence,
      body: remainder.length > 0 ? clipAtWord(remainder, 420) : "",
    };
  }
  return { thesis: clipAtWord(compact, 150), body: "" };
}

/**
 * Invalidates every memory query variant plus the derived archive surfaces
 * after a save. The generated keys use the full path as their first element,
 * so memory details need a predicate rather than a single literal prefix.
 */
export function invalidateMemoryQueries(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({
    predicate: (query) => {
      const [root] = query.queryKey;
      return typeof root === "string" && root.startsWith("/api/v1/memories");
    },
  });
  for (const key of [
    "/api/v1/stats",
    "/api/v1/timeline",
    "/api/v1/summaries",
    "/api/v1/search",
  ]) {
    void queryClient.invalidateQueries({ queryKey: [key] });
  }
}
