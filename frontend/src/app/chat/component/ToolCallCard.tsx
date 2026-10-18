import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { truncate } from "../../../lib/format";
import { formatArgumentValue } from "../format";
import { toolStatusTone } from "./status";
import type { ToolCallMeta, ToolResultMeta } from "../types";

interface ToolCallCardProps {
  readonly call: ToolCallMeta;
  readonly result: ToolResultMeta | null;
  readonly index: number;
}

/** A structured tool call, with status and duration from its matching result. */
export function ToolCallCard({ call, result, index }: ToolCallCardProps) {
  const status = result?.status ?? null;
  const argumentsList = call.arguments
    ? Object.entries(call.arguments)
    : [];
  const statusLabel = status ?? (result ? "recorded" : "awaiting result");

  let argumentsBody: ReactNode;
  if (argumentsList.length > 0) {
    argumentsBody = (
      <dl className="chat-tool__args">
        {argumentsList.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{formatArgumentValue(value)}</dd>
          </div>
        ))}
      </dl>
    );
  } else if (call.rawArguments) {
    argumentsBody = (
      <pre className="chat-tool__raw">{truncate(call.rawArguments, 600)}</pre>
    );
  } else {
    argumentsBody = <p className="chat-tool__empty">No arguments were recorded.</p>;
  }

  return (
    <article className="chat-tool">
      <header className="chat-tool__head">
        <span className="chat-tool__index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="chat-tool__mark" aria-hidden="true">
          <Icon name="spark" size={13} />
        </span>
        <span className="chat-tool__name">{call.name}</span>
        <Badge tone={toolStatusTone(status)} className="chat-tool__status">
          {statusLabel}
        </Badge>
      </header>

      {argumentsBody}

      <footer className="chat-tool__foot">
        <span className="chat-tool__call-id" title={call.id}>
          {call.id}
        </span>
        {result?.durationMs !== null && result?.durationMs !== undefined ? (
          <span>{result.durationMs} ms</span>
        ) : null}
        {result?.errorCode ? (
          <span className="chat-tool__error-code">{result.errorCode}</span>
        ) : null}
      </footer>
    </article>
  );
}
