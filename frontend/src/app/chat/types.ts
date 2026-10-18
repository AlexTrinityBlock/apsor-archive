/**
 * Typed readers for the untyped `model` and `data` JSON columns on an entry.
 *
 * The API deliberately keeps those columns open-ended, so every UI reader
 * narrows `unknown` before rendering. Nothing here injects markup.
 */
import type { AgentEntrySchema } from "../generated-apis-types/schemas";

export type JsonRecord = Record<string, unknown>;

export interface CitationToken {
  readonly kind: "file" | "memory" | "media" | "summary";
  readonly id: number;
  readonly chunk: number | null;
}

export interface ResourceMeta {
  readonly resourceType: "file" | "media" | "memory";
  readonly resourceId: number | null;
  readonly viewerUrl: string | null;
  readonly title: string | null;
  readonly mimeType: string | null;
  readonly rawFilePath: string | null;
  readonly chunk: number | null;
}

export interface AssistantMeta {
  readonly finishReason: string | null;
  readonly usage: Readonly<Record<string, number>>;
  readonly model: string | null;
  readonly provider: string | null;
  readonly step: number | null;
  readonly citations: readonly string[];
  readonly error: { readonly code: string; readonly detail: string } | null;
}

export interface ToolCallMeta {
  readonly id: string;
  readonly name: string;
  readonly arguments: JsonRecord | null;
  readonly rawArguments: string | null;
}

export interface ToolResultMeta {
  readonly tool: string | null;
  readonly status: string | null;
  readonly errorCode: string | null;
  readonly durationMs: number | null;
  readonly arguments: JsonRecord | null;
  readonly resource: ResourceMeta | null;
}

export interface ToolResultInfo {
  readonly entry: AgentEntrySchema;
  readonly callId: string | null;
  readonly meta: ToolResultMeta;
}

export interface SystemVersions {
  readonly promptVersion: string | null;
  readonly toolsVersion: string | null;
}

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null;
}

export function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function usageValue(value: unknown): Readonly<Record<string, number>> {
  const record = asRecord(value);
  if (!record) {
    return {};
  }
  const usage: Record<string, number> = {};
  for (const [key, item] of Object.entries(record)) {
    const parsed = numberValue(item);
    if (parsed !== null) {
      usage[key] = parsed;
    }
  }
  return usage;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const text = stringValue(item);
    return text ? [text] : [];
  });
}

function parseArguments(value: unknown): JsonRecord | null {
  if (isRecord(value)) {
    return value;
  }
  if (typeof value !== "string") {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return asRecord(parsed);
  } catch {
    return null;
  }
}

function assistantMessage(entry: AgentEntrySchema): JsonRecord | null {
  const message = entry.model?.find((item) => item.role === "assistant");
  return message ? asRecord(message) : null;
}

/** The keeper's words, stored in the model message rather than `data`. */
export function userText(entry: AgentEntrySchema): string {
  const message = entry.model?.find((item) => item.role === "user");
  return typeof message?.content === "string" ? message.content : "";
}

export function assistantText(entry: AgentEntrySchema): string {
  const content = assistantMessage(entry)?.content;
  return typeof content === "string" ? content : "";
}

export function readToolCalls(entry: AgentEntrySchema): ToolCallMeta[] {
  const raw = assistantMessage(entry)?.tool_calls;
  if (!Array.isArray(raw)) {
    return [];
  }

  const calls: ToolCallMeta[] = [];
  for (const item of raw) {
    const record = asRecord(item);
    if (!record) {
      continue;
    }
    const id = stringValue(record.id);
    const functionRecord = asRecord(record.function);
    const name = stringValue(functionRecord?.name);
    if (!id || !name) {
      continue;
    }
    const rawArguments =
      typeof functionRecord?.arguments === "string"
        ? functionRecord.arguments
        : null;
    calls.push({
      id,
      name,
      arguments: parseArguments(functionRecord?.arguments),
      rawArguments,
    });
  }
  return calls;
}

export function readAssistantMeta(entry: AgentEntrySchema): AssistantMeta {
  const data = asRecord(entry.data);
  const errorRecord = asRecord(data?.error);
  return {
    finishReason: stringValue(data?.finish_reason),
    usage: usageValue(data?.usage),
    model: stringValue(data?.model),
    provider: stringValue(data?.provider),
    step: numberValue(data?.step),
    citations: stringList(data?.citations),
    error: errorRecord
      ? {
          code: stringValue(errorRecord.code) ?? "agent_error",
          detail: stringValue(errorRecord.detail) ?? "The assistant step failed.",
        }
      : null,
  };
}

export function readToolResultCallId(entry: AgentEntrySchema): string | null {
  const message = entry.model?.find((item) => item.role === "tool");
  return message ? stringValue(message.tool_call_id) : null;
}

export function readToolResultMeta(entry: AgentEntrySchema): ToolResultMeta {
  const data = asRecord(entry.data);
  return {
    tool: stringValue(data?.tool),
    status: stringValue(data?.status),
    errorCode: stringValue(data?.error_code),
    durationMs: numberValue(data?.duration_ms),
    arguments: asRecord(data?.arguments),
    resource: readResource(data?.resource),
  };
}

export function readToolResultInfo(entry: AgentEntrySchema): ToolResultInfo {
  return {
    entry,
    callId: readToolResultCallId(entry),
    meta: readToolResultMeta(entry),
  };
}

export function readResource(value: unknown): ResourceMeta | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const resourceType = stringValue(record.resource_type);
  if (
    resourceType !== "file" &&
    resourceType !== "media" &&
    resourceType !== "memory"
  ) {
    return null;
  }
  return {
    resourceType,
    resourceId: numberValue(record.resource_id),
    viewerUrl: safeViewerPath(record.viewer_url),
    title: stringValue(record.title),
    mimeType: stringValue(record.mime_type),
    rawFilePath: stringValue(record.raw_file_path),
    chunk: numberValue(record.chunk),
  };
}

/** Only same-origin viewer paths are accepted as resource links. */
export function safeViewerPath(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const path = value.trim();
  if (!path.startsWith("/viewer/") || path.startsWith("//")) {
    return null;
  }
  for (const character of path) {
    const code = character.codePointAt(0) ?? 0;
    if (character === "\\" || code < 0x20 || code === 0x7f) {
      return null;
    }
  }

  const base =
    typeof window === "undefined" ? "http://localhost" : window.location.origin;
  try {
    const url = new URL(path, base);
    if (url.origin !== base || !url.pathname.startsWith("/viewer/")) {
      return null;
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

// The alternatives are literal and each digit run is anchored, so this is
// linear in the label length; the security plugin flags it heuristically.
// eslint-disable-next-line security/detect-unsafe-regex
const CITATION_LABEL = /^\[(file|memory|media|summary):(\d+)(?:#(\d+))?\]$/;

export function parseCitationLabel(value: string): CitationToken | null {
  const match = CITATION_LABEL.exec(value.trim());
  if (!match) {
    return null;
  }
  const kind = match[1];
  const id = Number(match[2]);
  const chunk = match[3] ? Number(match[3]) : null;
  if (
    (kind !== "file" &&
      kind !== "memory" &&
      kind !== "media" &&
      kind !== "summary") ||
    !Number.isSafeInteger(id) ||
    id <= 0 ||
    (chunk !== null && (!Number.isSafeInteger(chunk) || chunk <= 0))
  ) {
    return null;
  }
  return { kind, id, chunk };
}

export function citationLabel(token: CitationToken): string {
  const suffix = token.chunk === null ? "" : `#${token.chunk}`;
  return `[${token.kind}:${token.id}${suffix}]`;
}

export function citationHref(token: CitationToken): string | null {
  if (token.kind === "file") {
    const query = token.chunk === null ? "" : `?chunk=${token.chunk}`;
    return `/viewer/file/${token.id}${query}`;
  }
  if (token.kind === "media") {
    return `/viewer/media/${token.id}`;
  }
  if (token.kind === "memory") {
    return `/viewer/memory/${token.id}`;
  }
  return null;
}

export function noticeText(entry: AgentEntrySchema): string {
  const data = asRecord(entry.data);
  return (
    stringValue(data?.message) ??
    stringValue(data?.text) ??
    stringValue(data?.detail) ??
    stringValue(data?.notice) ??
    "A quiet note was added to this thread."
  );
}

export function systemVersions(entries: readonly AgentEntrySchema[]): SystemVersions {
  const system = entries.find((entry) => entry.kind === "pi.system");
  const data = asRecord(system?.data);
  return {
    promptVersion: stringValue(data?.prompt_version),
    toolsVersion: stringValue(data?.tools_version),
  };
}

export function mergeEntries(
  first: readonly AgentEntrySchema[],
  second: readonly AgentEntrySchema[],
): AgentEntrySchema[] {
  if (second.length === 0) {
    return [...first];
  }
  const byId = new Map<number, AgentEntrySchema>();
  for (const entry of first) {
    byId.set(entry.id, entry);
  }
  for (const entry of second) {
    byId.set(entry.id, entry);
  }
  return [...byId.values()].sort((left, right) => left.id - right.id);
}
