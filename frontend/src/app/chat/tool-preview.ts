/**
 * Bounded, human-readable previews of one structured tool result.
 *
 * The model-facing XML is never read here. Only the `data` payload that the
 * backend already records for the interface is narrowed into a few small
 * shapes, and every string is clipped. A generic result becomes a short
 * key/value list; arrays and objects are summarized by count and a sample
 * label instead of being serialized as JSON.
 */
import { readCalculationResult } from "./plot";
import { isRecord, numberValue, stringValue, type JsonRecord } from "./types";

const DETAIL_TEXT_LIMIT = 2_000;
const HIT_EXCERPT_LIMIT = 600;
const FIELD_VALUE_LIMIT = 160;
const MAX_PREVIEW_ITEMS = 12;

const META_KEYS = new Set([
  "tool",
  "status",
  "duration_ms",
  "error_code",
  "truncated",
  "tool_truncated",
  "arguments",
  "resource",
  "detail",
  "cached",
  "provider",
  "retrieved_at",
  "query",
  "result_number",
]);

export interface ToolPreviewHit {
  readonly title: string | null;
  readonly url: string | null;
  readonly excerpt: string;
}

export interface ToolPreviewExcerpt {
  readonly label: string;
  readonly title: string | null;
  readonly excerpt: string;
}

export interface ToolPreviewField {
  readonly key: string;
  readonly value: string;
}

export interface ToolPreviewCollection {
  readonly key: string;
  readonly count: number;
  readonly label: string | null;
  readonly unit: "items" | "fields";
}

export type ToolPreview =
  | {
      readonly kind: "search";
      readonly hits: readonly ToolPreviewHit[];
      readonly total: number;
      readonly truncated: boolean;
    }
  | {
      readonly kind: "fetch";
      readonly url: string | null;
      readonly page: number | null;
      readonly totalPages: number | null;
      readonly hasMore: boolean;
      readonly content: string;
      readonly contentChars: number | null;
      readonly truncated: boolean;
    }
  | {
      readonly kind: "excerpts";
      readonly items: readonly ToolPreviewExcerpt[];
      readonly total: number;
    }
  | {
      readonly kind: "text";
      readonly title: string | null;
      readonly text: string;
    }
  | {
      readonly kind: "calculation";
      readonly expression: string;
      readonly formatted: string;
    }
  | {
      readonly kind: "fields";
      readonly fields: readonly ToolPreviewField[];
      readonly collections: readonly ToolPreviewCollection[];
    }
  | { readonly kind: "none" };

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null;
}

function recordList(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const record = asRecord(item);
    return record ? [record] : [];
  });
}

function scalarText(value: unknown): string | null {
  if (typeof value === "string") {
    return stringValue(value);
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function clip(value: string, limit: number): string {
  const trimmed = value.trim();
  return trimmed.length > limit
    ? `${trimmed.slice(0, limit - 1).trimEnd()}…`
    : trimmed;
}

function isTruncated(data: JsonRecord): boolean {
  return data.truncated === true || data.tool_truncated === true;
}

function sampleLabel(value: unknown): string | null {
  const record = asRecord(value);
  if (!record) {
    return scalarText(value);
  }
  for (const key of [
    "title",
    "file_name",
    "raw_file_path",
    "path",
    "name",
    "url",
    "kind",
  ]) {
    const label = stringValue(record[key]);
    if (label) {
      return label;
    }
  }
  return null;
}

function webSearchPreview(data: JsonRecord): ToolPreview {
  const rows = recordList(data.results);
  const hits: ToolPreviewHit[] = rows
    .slice(0, MAX_PREVIEW_ITEMS)
    .map((result) => ({
      title: stringValue(result.title),
      url: stringValue(result.url),
      excerpt: clip(stringValue(result.excerpt) ?? "", HIT_EXCERPT_LIMIT),
    }));
  if (hits.length === 0) {
    return { kind: "none" };
  }
  return {
    kind: "search",
    hits,
    total: rows.length,
    truncated: isTruncated(data),
  };
}

function webFetchPreview(data: JsonRecord): ToolPreview {
  const content = clip(stringValue(data.content) ?? "", DETAIL_TEXT_LIMIT);
  if (content.length === 0) {
    return { kind: "none" };
  }
  return {
    kind: "fetch",
    url: stringValue(data.url),
    page: numberValue(data.page),
    totalPages: numberValue(data.total_pages),
    hasMore: data.has_more === true,
    content,
    contentChars: numberValue(data.content_chars),
    truncated: data.source_truncated === true || data.truncated === true,
  };
}

function memoryPreview(data: JsonRecord): ToolPreview {
  const target =
    asRecord(data.target) ?? asRecord(data.memory) ?? asRecord(data.saved);
  const content =
    stringValue(target?.content) ??
    stringValue(data.content) ??
    stringValue(data.detail);
  if (!content) {
    return { kind: "none" };
  }
  return {
    kind: "text",
    title: stringValue(target?.title),
    text: clip(content, DETAIL_TEXT_LIMIT),
  };
}

function filePreview(data: JsonRecord): ToolPreview {
  const chunks = recordList(data.chunks).flatMap((chunk) => {
    const content = stringValue(chunk.content) ?? stringValue(chunk.excerpt);
    return content ? [content] : [];
  });
  const content =
    chunks.join("\n\n") ||
    stringValue(data.content) ||
    stringValue(data.excerpt);
  if (!content) {
    return { kind: "none" };
  }
  return {
    kind: "text",
    title: stringValue(data.file_name) ?? stringValue(data.raw_file_path),
    text: clip(content, DETAIL_TEXT_LIMIT),
  };
}

function knowledgePreview(data: JsonRecord): ToolPreview {
  const items: ToolPreviewExcerpt[] = [];
  const add = (
    label: string,
    rows: readonly JsonRecord[],
    titleKey: string | null,
  ): void => {
    for (const row of rows) {
      const excerpt = stringValue(row.excerpt);
      if (!excerpt) {
        continue;
      }
      items.push({
        label,
        title: titleKey ? stringValue(row[titleKey]) : null,
        excerpt: clip(excerpt, HIT_EXCERPT_LIMIT),
      });
    }
  };
  add("file", recordList(data.file_results), "raw_file_path");
  add("memory", recordList(data.memory_results), "title");
  add("summary", recordList(data.summary_results), null);
  add("history", recordList(data.history_results), null);
  if (items.length === 0) {
    return { kind: "none" };
  }
  return {
    kind: "excerpts",
    items: items.slice(0, MAX_PREVIEW_ITEMS),
    total: items.length,
  };
}

function historyPreview(data: JsonRecord): ToolPreview {
  const content = stringValue(data.content);
  if (!content) {
    return { kind: "none" };
  }
  return {
    kind: "text",
    title:
      stringValue(data.conversation_title) ??
      stringValue(data.role) ??
      null,
    text: clip(content, DETAIL_TEXT_LIMIT),
  };
}

function timelinePreview(data: JsonRecord): ToolPreview {
  const items: ToolPreviewExcerpt[] = recordList(data.events).flatMap(
    (event) => {
      const excerpt = stringValue(event.content);
      if (!excerpt) {
        return [];
      }
      return [
        {
          label: stringValue(event.kind) ?? "event",
          title: null,
          excerpt: clip(excerpt, HIT_EXCERPT_LIMIT),
        },
      ];
    },
  );
  if (items.length === 0) {
    return { kind: "none" };
  }
  return {
    kind: "excerpts",
    items: items.slice(0, MAX_PREVIEW_ITEMS),
    total: items.length,
  };
}

function calculationPreview(data: JsonRecord): ToolPreview {
  const calculation = readCalculationResult(data);
  if (calculation) {
    return {
      kind: "calculation",
      expression: calculation.expression,
      formatted: calculation.formatted,
    };
  }
  const expression = stringValue(data.expression);
  const formatted = stringValue(data.formatted);
  if (!expression || !formatted) {
    return { kind: "none" };
  }
  return { kind: "calculation", expression, formatted };
}

function genericPreview(data: JsonRecord): ToolPreview {
  const fields: ToolPreviewField[] = [];
  const collections: ToolPreviewCollection[] = [];
  for (const [key, value] of Object.entries(data)) {
    if (META_KEYS.has(key)) {
      continue;
    }
    const scalar = scalarText(value);
    if (scalar !== null) {
      fields.push({ key, value: clip(scalar, FIELD_VALUE_LIMIT) });
      continue;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        continue;
      }
      collections.push({
        key,
        count: value.length,
        label: sampleLabel(value[0]),
        unit: "items",
      });
      continue;
    }
    const record = asRecord(value);
    if (record) {
      const count = Object.keys(record).length;
      if (count === 0) {
        continue;
      }
      collections.push({
        key,
        count,
        label: sampleLabel(record),
        unit: "fields",
      });
    }
  }
  if (fields.length === 0 && collections.length === 0) {
    return { kind: "none" };
  }
  return { kind: "fields", fields, collections };
}

/** Build the bounded preview for one tool result. */
export function buildToolPreview(
  tool: string | null,
  data: JsonRecord | null,
): ToolPreview {
  if (!data) {
    return { kind: "none" };
  }
  switch (tool) {
    case "web_search":
      return webSearchPreview(data);
    case "web_fetch":
      return webFetchPreview(data);
    case "read_memory":
    case "save_memory":
      return memoryPreview(data);
    case "read_file":
      return filePreview(data);
    case "search_knowledge":
      return knowledgePreview(data);
    case "history_message":
      return historyPreview(data);
    case "read_timeline":
      return timelinePreview(data);
    case "calculate":
      return calculationPreview(data);
    default:
      return genericPreview(data);
  }
}
