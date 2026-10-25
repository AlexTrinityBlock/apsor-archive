import { memo, type ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { formatNumber } from "../../../lib/format";
import type {
  ChatStreamTool,
  ChatStreamView,
} from "../hook/useChatStream";
import type {
  CitationToken,
  ResourceMeta,
  ToolCallMeta,
  ToolResultMeta,
} from "../types";
import { MarkdownBody } from "./MarkdownBody";
import { ResourceCard } from "./ResourceCard";
import { ToolCallCard } from "./ToolCallCard";
import { UserMarginalia } from "./UserMarginalia";
import { finishReasonTone } from "./status";

interface StreamingTurnProps {
  readonly stream: ChatStreamView;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}

function asCall(tool: ChatStreamTool): ToolCallMeta {
  return {
    id: tool.id,
    name: tool.name,
    arguments: tool.arguments,
    rawArguments: null,
  };
}

function pageContextLabel(stream: ChatStreamView): string {
  if (!stream.pageContextAttached) {
    return "This page is already attached to the thread";
  }
  if (stream.pageContextEntryId === null) {
    return "Page context captured";
  }
  return `Page context captured · entry #${stream.pageContextEntryId}`;
}

function asResult(tool: ChatStreamTool): ToolResultMeta {
  return {
    tool: tool.name,
    status: tool.status,
    errorCode: tool.errorCode,
    durationMs: tool.durationMs,
    arguments: tool.arguments,
    resource: tool.resource,
    data: tool.data,
    detail: null,
  };
}

/** The optimistic turn shown while the SSE stream is open. */
export const StreamingTurn = memo(function StreamingTurn({
  stream,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
  onOpenResource,
}: StreamingTurnProps) {
  const total = stream.usage.total_tokens;

  let liveBody: ReactNode = null;
  if (stream.status === "waiting") {
    liveBody = (
      <p className="chat-turn__silent is-live" role="status">
        <span className="chat-pulse" aria-hidden="true" />
        Waiting for your approval before the write can continue.
      </p>
    );
  } else if (stream.assistantText.length > 0) {
    liveBody = (
      <div className="chat-turn__bubble">
        <MarkdownBody
          markdown={stream.assistantText}
          onOpenCitation={onOpenCitation}
        />
      </div>
    );
  } else if (!stream.error) {
    liveBody = (
      <p className="chat-turn__silent is-live">
        <span className="chat-pulse" aria-hidden="true" />
        {stream.toolCalls.length > 0
          ? "The tools are being read."
          : "Waiting for the first line…"}
      </p>
    );
  }

  return (
    <div className="chat-live-turn" aria-busy={stream.status === "running"}>
      {stream.userContent.length > 0 ? (
        <UserMarginalia text={stream.userContent} pending />
      ) : null}

      <article className="chat-turn chat-turn--agent is-live">
        <header className="chat-turn__author">
          <span className="chat-turn__mark chat-turn__mark--agent" aria-hidden="true">
            <span className="chat-pulse" />
          </span>
          <span>Apsor Archive Agent</span>
          <span className="chat-turn__meta">
            {stream.runId === null ? "opening a run" : `run #${stream.runId}`}
          </span>
          {stream.finishReason ? (
            <Badge tone={finishReasonTone(stream.finishReason)}>
              {stream.finishReason}
            </Badge>
          ) : null}
        </header>

        {stream.toolCalls.length > 0 ? (
          <div className="chat-tool-flow">
            {stream.toolCalls.map((tool, index) => (
              <div className="chat-stream-tool" key={tool.id}>
                <ToolCallCard
                  call={asCall(tool)}
                  result={asResult(tool)}
                  index={index}
                  selected={selectedTraceId === tool.id}
                  onSelect={onSelectTrace}
                />
                {tool.resource ? (
                  <ResourceCard
                    resource={tool.resource}
                    onOpen={onOpenResource}
                  />
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {liveBody}

        {stream.pageContextKey !== null && stream.runId !== null ? (
          <p className="chat-context-live">
            <Icon name="layers" size={12} />
            {pageContextLabel(stream)}
          </p>
        ) : null}

        {stream.error ? (
          <div className="chat-turn__error" role="status">
            <Icon name="info" size={15} />
            <div>
              <strong>{stream.error.code}</strong>
              <p>{stream.error.detail}</p>
            </div>
          </div>
        ) : null}

        {total !== undefined && total > 0 ? (
          <p className="chat-turn__usage-note">
            {formatNumber(total)} tokens on this turn
          </p>
        ) : null}
      </article>
    </div>
  );
});
