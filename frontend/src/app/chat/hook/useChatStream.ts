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
import {
  getActiveLocale,
  translate,
  translateApiErrorWithActiveLocale,
} from "../../i18n";
import { invalidateConversation } from "../query";
import type { ChatAttachmentView } from "../types";
import {
  applyStreamEvents,
  createStreamView,
  isDeltaEvent,
  type ChatStreamView,
} from "./stream-reducer";

export type {
  ChatStreamSegment,
  ChatStreamTool,
  ChatStreamView,
} from "./stream-reducer";

interface UseChatStreamResult {
  readonly stream: ChatStreamView | null;
  readonly isStreaming: boolean;
  readonly start: (
    conversationId: number,
    content: string,
    pageContext?: AgentPageContextPayload,
    attachments?: readonly ChatAttachmentView[],
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
    return translateApiErrorWithActiveLocale(
      error,
      "chat.errors.agentUnanswered",
    );
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return translate(getActiveLocale(), "chat.errors.agentUnanswered");
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
      userAttachments: readonly ChatAttachmentView[],
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
      setStream(
        createStreamView(
          conversationId,
          userContent,
          userAttachments,
          pageContextKey,
        ),
      );

      // Token deltas are buffered to one state update per animation frame;
      // any structural event flushes the buffer first so order never changes.
      let pending: AgentStreamEvent[] = [];
      let frame: number | null = null;
      const flush = () => {
        if (frame !== null) {
          cancelAnimationFrame(frame);
          frame = null;
        }
        if (pending.length === 0 || !mountedRef.current) {
          pending = [];
          return;
        }
        const batch = pending;
        pending = [];
        setStream((current) =>
          current ? applyStreamEvents(current, batch) : current,
        );
      };

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
        pending.push(event);
        if (!isDeltaEvent(event)) {
          flush();
        } else if (frame === null) {
          frame = requestAnimationFrame(() => {
            frame = null;
            flush();
          });
        }
      };

      try {
        await execute(controller.signal, handleEvent);
        if (!terminal && !controller.signal.aborted) {
          ok = false;
          onErrorRef.current(
            translate(getActiveLocale(), "chat.errors.streamClosed"),
          );
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          ok = false;
          onErrorRef.current(describeError(error));
        }
      } finally {
        flush();
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
      attachments: readonly ChatAttachmentView[] = [],
    ) => {
      const trimmed = content.trim();
      if (trimmed.length === 0 && attachments.length === 0) {
        return;
      }
      await runTurn(
        conversationId,
        trimmed,
        attachments,
        pageContext?.key ?? null,
        (signal, onEvent) =>
          streamAgentMessage({
            conversationId,
            content: trimmed,
            attachmentIds: attachments.map((attachment) => attachment.id),
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
        [],
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
        [],
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
