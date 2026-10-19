import { memo, type ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { formatNumber } from "../../../lib/format";
import type {
  ChatStreamTool,
  ChatStreamView,
} from "../hook/useChatStream";
import type { ToolCallMeta, ToolResultMeta } from "../types";
import { MarkdownBody } from "./MarkdownBody";
import { ResourceCard } from "./ResourceCard";
import { ToolCallCard } from "./ToolCallCard";
import { UserMarginalia } from "./UserMarginalia";
import { finishReasonTone } from "./status";

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
  return "Page context captured · entry #" + stream.pageContextEntryId;
}

function asResult(tool: ChatStreamTool): ToolResultMeta {
  return {
    tool: tool.name,
    status: tool.status,
    errorCode: null,
    durationMs: null,
    arguments: tool.arguments,
    resource: tool.resource,
    data: tool.data,
    detail: null,
  };
}

/** The optimistic turn shown while the SSE stream is open. */
export const StreamingTurn = memo(function StreamingTurn({
  stream,
}: {
  readonly stream: ChatStreamView;
}) {
  const total = stream.usage.total_tokens;

  let liveBody: ReactNode = null;
  if (stream.status === "waiting") {
    liveBody = (
      <p className="chat-sheet__silent chat-sheet__silent--live" role="status">
        <span className="chat-sheet__pulse" aria-hidden="true" />
        Waiting for your approval before the write can continue.
      </p>
    );
  } else if (stream.assistantText.length > 0) {
    liveBody = <MarkdownBody markdown={stream.assistantText} />;
  } else if (!stream.error) {
    liveBody = (
      <p className="chat-sheet__silent chat-sheet__silent--live">
        <span className="chat-sheet__pulse" aria-hidden="true" />
        {stream.toolCalls.length > 0
          ? "The tools are being read."
          : "Waiting for the first line…"}
      </p>
    );
  }

  return (
    <div className="chat-stream-turn" aria-busy={stream.status === "running"}>
      {stream.userContent.length > 0 ? (
        <UserMarginalia text={stream.userContent} pending />
      ) : null}
      <article className="chat-sheet chat-sheet--live">
        <header className="chat-sheet__head">
          <div className="chat-sheet__heading">
            <p className="eyebrow">Live sheet · listening</p>
            <p className="chat-sheet__model">
              {stream.runId === null ? "opening a run" : `run ${stream.runId}`}
            </p>
          </div>
          {stream.finishReason ? (
            <Badge tone={finishReasonTone(stream.finishReason)}>
              {stream.finishReason}
            </Badge>
          ) : (
            <span className="chat-sheet__pulse" aria-hidden="true" />
          )}
        </header>

        {liveBody}

        {stream.pageContextKey !== null && stream.runId !== null ? (
          <p className={stream.pageContextAttached ? "pi-context-live is-attached" : "pi-context-live"}>
            <Icon name="layers" size={12} />
            {pageContextLabel(stream)}
          </p>
        ) : null}

        {stream.toolCalls.length > 0 ? (
          <div className="chat-sheet__calls">
            {stream.toolCalls.map((tool, index) => (
              <div className="chat-stream-tool" key={tool.id}>
                <ToolCallCard
                  call={asCall(tool)}
                  result={asResult(tool)}
                  index={index}
                />
                {tool.resource ? (
                  <ResourceCard resource={tool.resource} />
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {stream.error ? (
          <div className="chat-sheet__error" role="status">
            <Icon name="info" size={16} />
            <div>
              <strong>{stream.error.code}</strong>
              <p>{stream.error.detail}</p>
            </div>
          </div>
        ) : null}

        {total !== undefined && total > 0 ? (
          <footer className="chat-sheet__foot">
            <p className="chat-stream-turn__usage">
              {formatNumber(total)} tokens on this turn
            </p>
          </footer>
        ) : null}
      </article>
    </div>
  );
});
