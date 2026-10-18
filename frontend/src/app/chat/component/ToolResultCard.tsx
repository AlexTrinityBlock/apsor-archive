import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { formatArgumentValue } from "../format";
import { readToolResultCallId, readToolResultMeta } from "../types";
import { ResourceCard } from "./ResourceCard";
import { toolStatusTone } from "./status";

/** A result card built from structured data, never the model-facing XML. */
export function ToolResultCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const meta = readToolResultMeta(entry);
  const callId = readToolResultCallId(entry);
  const argumentsList = meta.arguments ? Object.entries(meta.arguments) : [];

  return (
    <article className="chat-result">
      <header className="chat-result__head">
        <span className="chat-result__mark" aria-hidden="true">
          <Icon name="layers" size={15} />
        </span>
        <div className="chat-result__heading">
          <p className="eyebrow">Field note · tool result</p>
          <h3>{meta.tool ?? "Tool result"}</h3>
        </div>
        <Badge tone={toolStatusTone(meta.status)}>
          {meta.status ?? "recorded"}
        </Badge>
      </header>

      <p className="chat-result__meta">
        <span>entry #{entry.id}</span>
        {meta.durationMs === null ? null : <span>{meta.durationMs} ms</span>}
        {callId ? <span title={callId}>{callId}</span> : null}
        {meta.errorCode ? (
          <span className="chat-result__error-code">{meta.errorCode}</span>
        ) : null}
      </p>

      {meta.resource ? (
        <ResourceCard resource={meta.resource} />
      ) : (
        <p className="chat-result__note">
          The full tool result remains recorded in the transcript.
        </p>
      )}

      {argumentsList.length > 0 ? (
        <details className="chat-result__args">
          <summary>Arguments used</summary>
          <dl>
            {argumentsList.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{formatArgumentValue(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </article>
  );
}
