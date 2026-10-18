/**
 * Streaming transport for the persistent agent transcript.
 *
 * The generated Orval hook for `POST /agent/conversations/{id}/messages`
 * resolves a normal JSON response, so the browser uses this small fetch client
 * instead: it asks for `text/event-stream`, parses frames as they arrive, and
 * leaves persistence and query refresh to the caller.
 */
import { ApiError } from "./fetch-client";

export interface AgentPageContextPayload {
  readonly key: string;
  readonly path: string;
  readonly title: string | null;
  readonly text: string;
}

export interface AgentRunStartData {
  readonly run_id: number;
  readonly user_entry_id: number;
  readonly page_context_entry_id: number | null;
  readonly page_context_attached: boolean;
}

export interface AgentMessageStartData {
  readonly entry_id: number | null;
  readonly kind: string;
  readonly role: string | null;
}

export interface AgentMessageDeltaData {
  readonly entry_id: number | null;
  readonly delta: string;
}

export interface AgentMessageEndData {
  readonly entry_id: number | null;
  readonly usage: Readonly<Record<string, number>>;
  readonly finish_reason: string;
}

export interface AgentToolStartData {
  readonly entry_id: number | null;
  readonly tool_call_id: string;
  readonly name: string;
  readonly arguments: Readonly<Record<string, unknown>>;
}

export interface AgentToolEndData {
  readonly entry_id: number | null;
  readonly tool_call_id: string;
  readonly name: string;
  readonly status: string;
  readonly resource: unknown;
  readonly data: Readonly<Record<string, unknown>> | null;
  readonly duration_ms: number | null;
  readonly error_code: string | null;
}

export interface AgentRunEndData {
  readonly run_id: number;
  readonly status: string;
}

export interface AgentErrorData {
  readonly code: string;
  readonly detail: string;
}

/** One normalized event from the server-sent turn stream. */
export type AgentStreamEvent =
  | { readonly type: "run_start"; readonly data: AgentRunStartData }
  | { readonly type: "message_start"; readonly data: AgentMessageStartData }
  | { readonly type: "message_delta"; readonly data: AgentMessageDeltaData }
  | { readonly type: "message_end"; readonly data: AgentMessageEndData }
  | { readonly type: "tool_start"; readonly data: AgentToolStartData }
  | { readonly type: "tool_end"; readonly data: AgentToolEndData }
  | { readonly type: "run_end"; readonly data: AgentRunEndData }
  | { readonly type: "error"; readonly data: AgentErrorData };

export interface StreamAgentMessageOptions {
  readonly conversationId: number;
  readonly content: string;
  readonly pageContext?: AgentPageContextPayload;
  readonly requestId?: string;
  readonly signal?: AbortSignal;
  readonly onEvent: (event: AgentStreamEvent) => void;
}

type UnknownRecord = Record<string, unknown>;

interface SseFrame {
  readonly event: string;
  readonly data: string;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numericRecord(value: unknown): Readonly<Record<string, number>> {
  if (!isRecord(value)) {
    return {};
  }
  const result: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) {
    const parsed = numberValue(item);
    if (parsed !== null) {
      result[key] = parsed;
    }
  }
  return result;
}

function createRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(8);
    crypto.getRandomValues(bytes);
    const suffix = Array.from(bytes, (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    return `req-${Date.now().toString(36)}-${suffix}`;
  }
  return `req-${Date.now().toString(36)}`;
}

function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" &&
      error instanceof DOMException &&
      error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

/** Read enough of a failed response to keep FastAPI's stable error shape. */
async function readFailure(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    const text = await response.text();
    if (text.length > 0) {
      payload = JSON.parse(text) as unknown;
    }
  } catch {
    payload = null;
  }

  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("dendromatrix:unauthorized"));
  }

  const detail =
    (isRecord(payload) ? stringValue(payload.detail) : null) ??
    (isRecord(payload) ? stringValue(payload.error) : null) ??
    (response.statusText || `Request failed with status ${response.status}`);
  const code = (isRecord(payload) ? stringValue(payload.error) : null) ?? "http_error";
  return new ApiError(response.status, code, detail, payload);
}

function nextDelimiter(
  buffer: string,
): { readonly index: number; readonly length: number } | null {
  const candidates: ReadonlyArray<{ index: number; length: number }> = [
    { index: buffer.indexOf("\n\n"), length: 2 },
    { index: buffer.indexOf("\r\n\r\n"), length: 4 },
    { index: buffer.indexOf("\r\r"), length: 2 },
  ].filter((candidate) => candidate.index >= 0);

  if (candidates.length === 0) {
    return null;
  }
  return candidates.reduce((earliest, candidate) =>
    candidate.index < earliest.index ? candidate : earliest,
  );
}

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of raw.split(/\r\n|\n|\r/)) {
    if (line.length === 0 || line.startsWith(":")) {
      continue;
    }
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join("\n") };
}

/** Normalize one SSE frame into the small event union the UI understands. */
function toStreamEvent(frame: SseFrame): AgentStreamEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(frame.data) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }

  if (frame.event === "run_start") {
    const runId = numberValue(parsed.run_id);
    const userEntryId = numberValue(parsed.user_entry_id);
    if (runId === null || userEntryId === null) {
      return null;
    }
    return {
      type: "run_start",
      data: {
        run_id: runId,
        user_entry_id: userEntryId,
        page_context_entry_id: numberValue(parsed.page_context_entry_id),
        page_context_attached: parsed.page_context_attached === true,
      },
    };
  }

  if (frame.event === "message_start") {
    return {
      type: "message_start",
      data: {
        entry_id: numberValue(parsed.entry_id),
        kind: stringValue(parsed.kind) ?? "pi.assistant",
        role: stringValue(parsed.role),
      },
    };
  }

  if (frame.event === "message_delta") {
    const delta = stringValue(parsed.delta);
    if (delta === null) {
      return null;
    }
    return {
      type: "message_delta",
      data: { entry_id: numberValue(parsed.entry_id), delta },
    };
  }

  if (frame.event === "message_end") {
    return {
      type: "message_end",
      data: {
        entry_id: numberValue(parsed.entry_id),
        usage: numericRecord(parsed.usage),
        finish_reason: stringValue(parsed.finish_reason) ?? "unknown",
      },
    };
  }

  if (frame.event === "tool_start") {
    const callId = stringValue(parsed.tool_call_id);
    const name = stringValue(parsed.name);
    if (callId === null || name === null) {
      return null;
    }
    return {
      type: "tool_start",
      data: {
        entry_id: numberValue(parsed.entry_id),
        tool_call_id: callId,
        name,
        arguments: isRecord(parsed.arguments) ? parsed.arguments : {},
      },
    };
  }

  if (frame.event === "tool_end") {
    const callId = stringValue(parsed.tool_call_id);
    const name = stringValue(parsed.name);
    if (callId === null || name === null) {
      return null;
    }
    return {
      type: "tool_end",
      data: {
        entry_id: numberValue(parsed.entry_id),
        tool_call_id: callId,
        name,
        status: stringValue(parsed.status) ?? "unknown",
        resource: parsed.resource,
        data: isRecord(parsed.data) ? parsed.data : null,
        duration_ms: numberValue(parsed.duration_ms),
        error_code: stringValue(parsed.error_code),
      },
    };
  }

  if (frame.event === "run_end") {
    return {
      type: "run_end",
      data: {
        run_id: numberValue(parsed.run_id) ?? 0,
        status: stringValue(parsed.status) ?? "unknown",
      },
    };
  }

  if (frame.event === "error") {
    return {
      type: "error",
      data: {
        code: stringValue(parsed.code) ?? "agent_error",
        detail: stringValue(parsed.detail) ?? "The agent run failed.",
      },
    };
  }

  return null;
}

/**
 * POST one user message and consume its SSE turn stream.
 *
 * The promise resolves when the server closes the stream. Aborting `signal`
 * rejects the fetch, which the server treats as a client disconnect and a
 * cancellation request. Completed entries remain in the transcript.
 */
export async function streamAgentMessage({
  conversationId,
  content,
  pageContext,
  requestId,
  signal,
  onEvent,
}: StreamAgentMessageOptions): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `/api/v1/agent/conversations/${conversationId}/messages`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          content,
          request_id: requestId ?? createRequestId(),
          ...(pageContext ? { page_context: pageContext } : {}),
        }),
        signal,
      },
    );
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ApiError(
      0,
      "network_error",
      "The archive could not be reached.",
      null,
    );
  }

  if (!response.ok) {
    throw await readFailure(response);
  }
  if (!response.body) {
    throw new ApiError(
      502,
      "stream_unavailable",
      "The agent stream could not be opened.",
      null,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consume = (raw: string) => {
    const frame = parseFrame(raw);
    if (!frame) {
      return;
    }
    const event = toStreamEvent(frame);
    if (event) {
      onEvent(event);
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let delimiter = nextDelimiter(buffer);
      while (delimiter) {
        consume(buffer.slice(0, delimiter.index));
        buffer = buffer.slice(delimiter.index + delimiter.length);
        delimiter = nextDelimiter(buffer);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim().length > 0) {
      consume(buffer);
    }
  } finally {
    reader.releaseLock();
  }
}
