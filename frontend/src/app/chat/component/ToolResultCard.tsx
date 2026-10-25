import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { formatArgumentValue } from "../format";
import {
  readToolResultCallId,
  readToolResultMeta,
  type ResourceMeta,
} from "../types";
import { ResourceCard } from "./ResourceCard";
import { toolStatusLabel, toolStatusTone } from "./status";

/** A result card built from structured data, never the model-facing XML. */
export function ToolResultCard({
  entry,
  onOpenResource,
}: {
  readonly entry: AgentEntrySchema;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}) {
  const { t, formatNumber } = useI18n();
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
          <p className="eyebrow">{t("chat.tool.resultEyebrow")}</p>
          <h3>{meta.tool ?? t("chat.tool.resultFallback")}</h3>
        </div>
        <Badge tone={toolStatusTone(meta.status)}>
          {toolStatusLabel(
            meta.status,
            t,
            t("chat.common.recorded"),
          )}
        </Badge>
      </header>

      <p className="chat-result__meta">
        <span>{t("chat.tool.entry", { id: entry.id })}</span>
        {meta.durationMs === null ? null : (
          <span>{formatNumber(meta.durationMs)} ms</span>
        )}
        {callId ? <span title={callId}>{callId}</span> : null}
        {meta.errorCode ? (
          <span className="chat-result__error-code">{meta.errorCode}</span>
        ) : null}
      </p>

      {meta.resource ? (
        <ResourceCard resource={meta.resource} onOpen={onOpenResource} />
      ) : (
        <p className="chat-result__note">{t("chat.tool.resultNote")}</p>
      )}

      {argumentsList.length > 0 ? (
        <details className="chat-result__args">
          <summary>{t("chat.tool.argumentsUsed")}</summary>
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
