/**
 * Owns one live agent turn: optimistic text, tool cards, cancellation, and the
 * scoped refetch that replaces the live view with persisted entries.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../../apis/fetch-client";
import {
  streamAgentApproval,
  streamAgentMessage,
  streamAgentRetry,
  type AgentPageContextPayload,
  type AgentStreamEvent,
} from "../../../apis/agent-stream";
import { invalidateConversation } from "../query";
import { readResource, type JsonRecord, type ResourceMeta } from "../types";

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

export interface ChatStreamView {
  readonly conversationId: number;
  readonly userContent: string;
  readonly assistantText: string;
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

interface UseChatStreamResult {
  readonly stream: ChatStreamView | null;
  readonly isStreaming: boolean;
  readonly start: (
    conversationId: number,
    content: string,
    pageContext?: AgentPageContextPayload,
  ) => Promise<void>;
  readonly retry: (conversationId: number, userContent?: string) => Promise<void>;
  readonly resolveApproval: (
    conversationId: number,
    approvalId: number,
    decision: "approve" | "reject",
  ) => Promise<boolean>;
  readonly stop: () => void;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The agent could not answer.";
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

function applyEvent(
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
    case "message_start": {
      // A new assistant step after tools starts a fresh prose run; the
      // persisted transcript will replace this live view when it settles.
      const newStep = state.toolCalls.length > 0;
      return {
        ...state,
        assistantText: newStep ? "" : state.assistantText,
        finishReason: newStep ? null : state.finishReason,
        usage: newStep ? {} : state.usage,
        status: "running",
      };
    }
    case "message_delta":
      return {
        ...state,
        assistantText: state.assistantText + event.data.delta,
      };
    case "message_end":
      return {
        ...state,
        usage: event.data.usage,
        finishReason: event.data.finish_reason,
      };
    case "tool_start":
      return {
        ...state,
        toolCalls: upsertTool(state.toolCalls, event.data.tool_call_id, {
          name: event.data.name,
          arguments: event.data.arguments,
          status: "running",
          entryId: event.data.entry_id,
        }),
      };
    case "tool_end":
      return {
        ...state,
        toolCalls: upsertTool(state.toolCalls, event.data.tool_call_id, {
          name: event.data.name,
          status: event.data.status,
          resource: readResource(event.data.resource),
          entryId: event.data.entry_id,
          data: event.data.data,
          durationMs: event.data.duration_ms,
          errorCode: event.data.error_code,
        }),
      };
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

/** Starts, feeds, and cancels the single active turn for the chat page. */
export function useChatStream(
  onError: (message: string) => void,
): UseChatStreamResult {
  const queryClient = useQueryClient();
  const [stream, setStream] = useState<ChatStreamView | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const activeRef = useRef(false);
  const mountedRef = useRef(true);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const runTurn = useCallback(
    async (
      conversationId: number,
      userContent: string,
      pageContextKey: string | null,
      execute: (
        signal: AbortSignal,
        onEvent: (event: AgentStreamEvent) => void,
      ) => Promise<void>,
    ): Promise<boolean> => {
      if (activeRef.current) {
        return false;
      }

      activeRef.current = true;
      let ok = true;
      const controller = new AbortController();
      controllerRef.current = controller;
      setStream({
        conversationId,
        userContent,
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
      });

      let terminal = false;
      const handleEvent = (event: AgentStreamEvent) => {
        if (event.type === "error") {
          ok = false;
          onErrorRef.current(event.data.detail);
        }
        if (event.type === "run_end" || event.type === "error") {
          terminal = true;
        }
        if (!mountedRef.current) {
          return;
        }
        setStream((current) =>
          current ? applyEvent(current, event) : current,
        );
      };

      try {
        await execute(controller.signal, handleEvent);
        if (!terminal && !controller.signal.aborted) {
          ok = false;
          onErrorRef.current("The stream closed before the run finished.");
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          ok = false;
          onErrorRef.current(describeError(error));
        }
      } finally {
        try {
          await invalidateConversation(queryClient, conversationId);
        } catch {
          // The stream still settles; the next read can refetch the thread.
        } finally {
          activeRef.current = false;
          controllerRef.current = null;
          if (mountedRef.current) {
            setStream(null);
          }
        }
      }
      return ok;
    },
    [queryClient],
  );

  const start = useCallback(
    async (
      conversationId: number,
      content: string,
      pageContext?: AgentPageContextPayload,
    ) => {
      const trimmed = content.trim();
      if (trimmed.length === 0) {
        return;
      }
      await runTurn(
        conversationId,
        trimmed,
        pageContext?.key ?? null,
        (signal, onEvent) =>
          streamAgentMessage({
            conversationId,
            content: trimmed,
            pageContext,
            signal,
            onEvent,
          }),
      );
    },
    [runTurn],
  );

  const retry = useCallback(
    async (conversationId: number, userContent?: string) => {
      const content = userContent?.trim() ?? "";
      await runTurn(
        conversationId,
        content,
        null,
        (signal, onEvent) =>
          streamAgentRetry({
            conversationId,
            signal,
            onEvent,
          }),
      );
    },
    [runTurn],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const resolveApproval = useCallback(
    async (
      conversationId: number,
      approvalId: number,
      decision: "approve" | "reject",
    ) => {
      return runTurn(
        conversationId,
        "",
        null,
        (signal, onEvent) =>
          streamAgentApproval({
            approvalId,
            decision,
            signal,
            onEvent,
          }),
      );
    },
    [runTurn],
  );

  return { stream, isStreaming: stream !== null, start, retry, resolveApproval, stop };
}
