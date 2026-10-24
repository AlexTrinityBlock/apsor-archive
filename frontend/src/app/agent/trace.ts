/**
 * A UI-only projection of recorded agent activity.
 *
 * Nothing here reads or invents hidden reasoning: every item comes from a
 * persisted assistant/tool entry or from a transport event the server already
 * exposes. Tool `data` is the structured preview payload, not the XML content
 * sent to the model.
 */
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import {
  assistantText,
  isRecord,
  numberValue,
  readAssistantMeta,
  readToolCalls,
  readToolResultInfo,
  safeViewerPath,
  stringValue,
  type AssistantMeta,
  type JsonRecord,
  type ResourceMeta,
  type ToolResultInfo,
} from "../chat/types";
import type {
  ChatStreamTool,
  ChatStreamView,
} from "../chat/hook/useChatStream";

export type WorkPhase =
  | "orienting"
  | "searching"
  | "reading"
  | "comparing"
  | "composing"
  | "saving"
  | "sealed"
  | "error";

export type TraceKind = "tool" | "assistant" | "error" | "orienting";

export interface TraceItem {
  readonly id: string;
  readonly kind: TraceKind;
  readonly name: string;
  readonly tool: string | null;
  readonly step: number | null;
  readonly status: string;
  readonly arguments: JsonRecord | null;
  readonly data: JsonRecord | null;
  readonly durationMs: number | null;
  readonly errorCode: string | null;
  readonly detail: string | null;
  readonly resource: ResourceMeta | null;
  readonly entryId: number | null;
  readonly text: string | null;
  readonly createdAt: string | null;
  readonly live: boolean;
}

export interface TerminalTrace {
  readonly phase: WorkPhase;
  readonly status: string;
  readonly detail: string | null;
}

export interface WorkTraceModel {
  readonly items: readonly TraceItem[];
  readonly terminal: TerminalTrace | null;
}

export interface ResourceTarget {
  readonly type: "file" | "memory";
  readonly id: number;
  readonly chunk: number | null;
  readonly title: string | null;
}

const TOOL_PHASES: Readonly<Record<string, WorkPhase>> = {
  search_knowledge: "searching",
  read_file: "reading",
  read_timeline: "reading",
  read_path: "reading",
  read_memory: "comparing",
  save_memory: "saving",
  present_resource: "composing",
};

const PHASE_LABELS: Readonly<Record<WorkPhase, string>> = {
  orienting: "Orienting",
  searching: "Searching",
  reading: "Reading",
  comparing: "Comparing",
  composing: "Composing",
  saving: "Saving",
  sealed: "Sealed",
  error: "Needs repair",
};

export function phaseLabel(phase: WorkPhase): string {
  return PHASE_LABELS[phase];
}

export function phaseForItem(item: TraceItem): WorkPhase {
  if (item.status.toLowerCase() === "error" || item.kind === "error") {
    return "error";
  }
  if (item.kind === "orienting") {
    return "orienting";
  }
  if (item.kind === "assistant") {
    return "composing";
  }
  return TOOL_PHASES[item.tool ?? item.name] ?? "reading";
}

/** The recorded phase for a persisted entry sequence. */
export function phaseForTool(name: string, status: string | null): WorkPhase {
  if (status?.toLowerCase() === "error") {
    return "error";
  }
  return TOOL_PHASES[name] ?? "reading";
}

/** The newest tool/error item, or the newest item when no tool has run. */
export function currentTraceIndex(items: readonly TraceItem[]): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.tool !== null || item.kind === "error") {
      return index;
    }
  }
  return items.length - 1;
}

export function traceLabel(item: TraceItem): string {
  if (item.kind === "error") {
    return "Tool error";
  }
  if (item.kind === "assistant") {
    return item.name === "orienting" ? "Orienting" : "Composing";
  }
  return item.tool ?? item.name;
}

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null;
}

function recordText(record: JsonRecord | null, key: string): string | null {
  return stringValue(record?.[key]);
}

function recordNumber(record: JsonRecord | null, key: string): number | null {
  return numberValue(record?.[key]);
}

function errorMeta(meta: AssistantMeta): string | null {
  return meta.error ? meta.error.detail : null;
}

function persistedToolItem(
  entry: AgentEntrySchema,
  call: ReturnType<typeof readToolCalls>[number],
  step: number,
): TraceItem {
  return {
    id: call.id,
    kind: "tool",
    name: call.name,
    tool: call.name,
    step,
    status: "awaiting result",
    arguments: call.arguments,
    data: null,
    durationMs: null,
    errorCode: null,
    detail: null,
    resource: null,
    entryId: entry.id,
    text: null,
    createdAt: entry.created_at,
    live: false,
  };
}

function assistantTraceItem(
  entry: AgentEntrySchema,
  step: number,
  meta: AssistantMeta,
  text: string,
): TraceItem {
  const error = meta.error;
  return {
    id: `assistant-${entry.id}`,
    kind: error ? "error" : "assistant",
    name: error ? "assistant" : "composing",
    tool: null,
    step,
    status: error ? "error" : (meta.finishReason ?? "recorded"),
    arguments: null,
    data: error ? { code: error.code, detail: error.detail } : null,
    durationMs: null,
    errorCode: error?.code ?? null,
    detail: errorMeta(meta),
    resource: null,
    entryId: entry.id,
    text: text.length > 0 ? text : null,
    createdAt: entry.created_at,
    live: false,
  };
}

function mergeToolResult(item: TraceItem, info: ToolResultInfo): TraceItem {
  const meta = info.meta;
  return {
    ...item,
    tool: meta.tool ?? item.tool,
    status: meta.status ?? item.status,
    arguments: meta.arguments ?? item.arguments,
    data: meta.data,
    durationMs: meta.durationMs,
    errorCode: meta.errorCode,
    detail: meta.detail,
    resource: meta.resource ?? item.resource,
    entryId: item.entryId ?? info.entry.id,
  };
}

interface PersistedTrace {
  readonly items: TraceItem[];
  readonly stepCount: number;
  readonly lastMeta: AssistantMeta | null;
}

function buildPersistedTrace(entries: readonly AgentEntrySchema[]): PersistedTrace {
  const items: TraceItem[] = [];
  const byCall = new Map<string, number>();
  let step = 0;
  let lastMeta: AssistantMeta | null = null;

  for (const entry of entries) {
    if (entry.kind === "pi.assistant") {
      step += 1;
      const meta = readAssistantMeta(entry);
      lastMeta = meta;
      const calls = readToolCalls(entry);
      if (calls.length > 0) {
        for (const call of calls) {
          byCall.set(call.id, items.length);
          items.push(persistedToolItem(entry, call, meta.step ?? step));
        }
      } else {
        const text = assistantText(entry);
        if (text.trim().length > 0 || meta.error) {
          items.push(assistantTraceItem(entry, meta.step ?? step, meta, text));
        }
      }
      continue;
    }

    if (entry.kind !== "pi.tool-result") {
      continue;
    }
    const info = readToolResultInfo(entry);
    const callId = info.callId;
    if (callId !== null) {
      const index = byCall.get(callId);
      if (index !== undefined) {
        items[index] = mergeToolResult(items[index], info);
        continue;
      }
    }
    items.push({
      id: callId ?? `result-${entry.id}`,
      kind: info.meta.status?.toLowerCase() === "error" ? "error" : "tool",
      name: info.meta.tool ?? "tool result",
      tool: info.meta.tool,
      step,
      status: info.meta.status ?? "recorded",
      arguments: info.meta.arguments,
      data: info.meta.data,
      durationMs: info.meta.durationMs,
      errorCode: info.meta.errorCode,
      detail: info.meta.detail,
      resource: info.meta.resource,
      entryId: entry.id,
      text: null,
      createdAt: entry.created_at,
      live: false,
    });
  }

  return { items, stepCount: step, lastMeta };
}

function liveToolItem(tool: ChatStreamTool): TraceItem {
  return {
    id: tool.id,
    kind: tool.status.toLowerCase() === "error" ? "error" : "tool",
    name: tool.name,
    tool: tool.name,
    step: null,
    status: tool.status,
    arguments: tool.arguments,
    data: tool.data,
    durationMs: tool.durationMs,
    errorCode: tool.errorCode,
    detail: recordText(tool.data, "detail"),
    resource: tool.resource,
    entryId: tool.entryId,
    text: null,
    createdAt: null,
    live: true,
  };
}

function liveItems(stream: ChatStreamView | null): TraceItem[] {
  if (!stream) {
    return [];
  }
  const items = stream.toolCalls.map(liveToolItem);
  const text = stream.assistantText.trim();
  if (text.length > 0) {
    items.push({
      id: "live-assistant",
      kind: "assistant",
      name: "composing",
      tool: null,
      step: null,
      status: "writing",
      arguments: null,
      data: null,
      durationMs: null,
      errorCode: null,
      detail: null,
      resource: null,
      entryId: null,
      text,
      createdAt: null,
      live: true,
    });
  } else if (stream.toolCalls.length === 0 && !stream.error) {
    items.push({
      id: "live-orienting",
      kind: "orienting",
      name: "orienting",
      tool: null,
      step: null,
      status: "running",
      arguments: null,
      data: null,
      durationMs: null,
      errorCode: null,
      detail: null,
      resource: null,
      entryId: null,
      text: null,
      createdAt: null,
      live: true,
    });
  }
  if (stream.error) {
    items.push({
      id: "live-error",
      kind: "error",
      name: "assistant",
      tool: null,
      step: null,
      status: "error",
      arguments: null,
      data: { code: stream.error.code, detail: stream.error.detail },
      durationMs: null,
      errorCode: stream.error.code,
      detail: stream.error.detail,
      resource: null,
      entryId: null,
      text: null,
      createdAt: null,
      live: true,
    });
  }
  return items;
}

function terminalFor(
  stream: ChatStreamView | null,
  persisted: PersistedTrace,
): TerminalTrace | null {
  if (stream) {
    if (stream.status === "failed") {
      return {
        phase: "error",
        status: "failed",
        detail: stream.error?.detail ?? null,
      };
    }
    if (stream.status === "done") {
      return { phase: "sealed", status: "sealed", detail: null };
    }
    return null;
  }
  if (persisted.lastMeta?.error) {
    return {
      phase: "error",
      status: "error",
      detail: persisted.lastMeta.error.detail,
    };
  }
  if (persisted.stepCount > 0) {
    return { phase: "sealed", status: "recorded", detail: null };
  }
  return null;
}

/** Build the recorded (non-live) trace once per entry page. */
export function buildPersistedWorkTrace(
  entries: readonly AgentEntrySchema[],
): WorkTraceModel {
  const persisted = buildPersistedTrace(entries);
  return {
    items: persisted.items,
    terminal: terminalFor(null, persisted),
  };
}

/** Merge persisted trace items with the live turn, keeping entry order. */
export function mergeWorkTrace(
  persisted: WorkTraceModel,
  stream: ChatStreamView | null,
): WorkTraceModel {
  if (!stream) {
    return persisted;
  }
  const merged = [...persisted.items];
  const seen = new Set(merged.map((item) => item.id));
  for (const item of liveItems(stream)) {
    if (!seen.has(item.id)) {
      merged.push(item);
      seen.add(item.id);
    }
  }
  return {
    items: merged,
    terminal: terminalFor(stream, {
      items: [],
      stepCount: 0,
      lastMeta: null,
    }),
  };
}

/** Convenience wrapper used by tests and one-off readers. */
export function buildWorkTrace(
  entries: readonly AgentEntrySchema[],
  stream: ChatStreamView | null,
): WorkTraceModel {
  return mergeWorkTrace(buildPersistedWorkTrace(entries), stream);
}

function idFrom(value: unknown): number | null {
  const parsed = numberValue(value);
  return parsed !== null && Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function targetFromResource(resource: ResourceMeta | null): ResourceTarget | null {
  if (!resource || resource.resourceId === null) {
    return null;
  }
  return {
    type: resource.resourceType,
    id: resource.resourceId,
    chunk: resource.chunk,
    title: resource.title,
  };
}

function targetFromRecord(
  type: ResourceTarget["type"],
  record: JsonRecord | null,
  idKeys: readonly string[],
): ResourceTarget | null {
  if (!record) {
    return null;
  }
  let id: number | null = null;
  for (const key of idKeys) {
    id = idFrom(record[key]);
    if (id !== null) {
      break;
    }
  }
  if (id === null) {
    return null;
  }
  return {
    type,
    id,
    chunk: recordNumber(record, "chunk") ?? recordNumber(record, "chunk_start"),
    title:
      recordText(record, "title") ??
      recordText(record, "file_name") ??
      recordText(record, "path") ??
      recordText(record, "raw_file_path"),
  };
}

/** The concrete resource a trace item points at, when one exists. */
export function itemResourceTarget(item: TraceItem): ResourceTarget | null {
  const direct = targetFromResource(item.resource);
  if (direct) {
    return direct;
  }
  const data = item.data;
  if (!data) {
    return null;
  }
  if (item.tool === "present_resource") {
    const resource = asRecord(data.resource);
    const type = recordText(resource, "resource_type");
    if (type === "file" || type === "memory") {
      const id = idFrom(resource?.resource_id);
      if (id !== null) {
        return {
          type,
          id,
          chunk: recordNumber(resource, "chunk"),
          title: recordText(resource, "title"),
        };
      }
    }
  }
  if (item.tool === "read_file" || item.tool === "read_path") {
    return targetFromRecord("file", data, ["file_id"]);
  }
  if (item.tool === "read_memory" || item.tool === "save_memory") {
    return targetFromRecord("memory", data, ["memory_id"]);
  }
  return null;
}

/** The library or memory destination for a known target. */
export function viewerHref(target: ResourceTarget): string {
  if (target.type === "file") {
    const chunk = target.chunk === null ? "" : `&chunk=${target.chunk}`;
    return `/library?tab=files&file=${target.id}${chunk}`;
  }
  return `/memory/${target.id}`;
}

/** Prefer the structured target; only fall back to archive-internal URLs. */
export function safeResourceUrl(value: unknown, target: ResourceTarget | null): string | null {
  if (target) {
    return viewerHref(target);
  }
  return safeViewerPath(value);
}

/** Read a numeric id from a record or argument bag. */
export function recordId(
  record: JsonRecord | null,
  ...keys: string[]
): number | null {
  if (!record) {
    return null;
  }
  for (const key of keys) {
    const id = idFrom(record[key]);
    if (id !== null) {
      return id;
    }
  }
  return null;
}

/** Narrow a JSON value to a record list. */
export function recordList(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const record = asRecord(item);
    return record ? [record] : [];
  });
}

/** Read a compact string from a record. */
export function textField(record: JsonRecord | null, key: string): string | null {
  return recordText(record, key);
}

/** Read a finite number from a record. */
export function numberField(record: JsonRecord | null, key: string): number | null {
  return recordNumber(record, key);
}

/** Read a string list from a record. */
export function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const text = stringValue(item);
    return text ? [text] : [];
  });
}

/** A short text excerpt with a stable fallback. */
export function excerptOf(
  record: JsonRecord | null,
  keys: readonly string[],
  limit = 420,
): string {
  if (!record) {
    return "";
  }
  for (const key of keys) {
    const value = recordText(record, key);
    if (value) {
      return value.length > limit ? `${value.slice(0, limit - 1).trimEnd()}…` : value;
    }
  }
  return "";
}
