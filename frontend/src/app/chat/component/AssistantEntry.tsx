import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import {
  assistantText,
  parseCitationLabel,
  readAssistantMeta,
  readToolCalls,
  type CitationToken,
  type ToolResultInfo,
} from "../types";
import { CitationChip } from "./CitationChip";
import { MarkdownBody } from "./MarkdownBody";
import { ToolCallCard } from "./ToolCallCard";
import { finishReasonTone } from "./status";

interface AssistantEntryProps {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
  readonly action?: ReactNode;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
}

function usageRows(
  usage: Readonly<Record<string, number>>,
): ReadonlyArray<{ label: string; value: number }> {
  const rows: Array<{ label: string; value: number }> = [
    { label: "prompt", value: usage.prompt_tokens ?? 0 },
    { label: "completion", value: usage.completion_tokens ?? 0 },
    { label: "total", value: usage.total_tokens ?? 0 },
    { label: "cache hit", value: usage.prompt_cache_hit_tokens ?? 0 },
    { label: "cache miss", value: usage.prompt_cache_miss_tokens ?? 0 },
  ];
  return rows.filter((row) => row.value > 0);
}

/** An archival assistant turn: tool step chips, prose, citations, and usage. */
export function AssistantEntry({
  entry,
  toolResults,
  action,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
}: AssistantEntryProps) {
  const meta = readAssistantMeta(entry);
  const text = assistantText(entry);
  const calls = readToolCalls(entry);
  const citations: CitationToken[] = [];
  const seenCitations = new Set<string>();
  for (const label of meta.citations) {
    const token = parseCitationLabel(label);
    if (!token) {
      continue;
    }
    const key = `${token.kind}:${token.id}:${token.chunk ?? ""}`;
    if (seenCitations.has(key)) {
      continue;
    }
    seenCitations.add(key);
    citations.push(token);
  }
  const usage = usageRows(meta.usage);

  let body: ReactNode = null;
  if (text.length > 0) {
    body = (
      <div className="chat-turn__bubble">
        <MarkdownBody markdown={text} onOpenCitation={onOpenCitation} />
      </div>
    );
  } else if (calls.length === 0 && !meta.error) {
    body = <p className="chat-turn__silent">No prose was recorded for this step.</p>;
  }

  return (
    <article className="chat-turn chat-turn--agent">
      <header className="chat-turn__author">
        <span className="chat-turn__mark chat-turn__mark--agent" aria-hidden="true">
          <Icon name="spark" size={11} />
        </span>
        <span>Apsor Archive Agent</span>
        <span className="chat-turn__meta">
          {[meta.provider, meta.model, meta.step === null ? null : `step ${meta.step}`]
            .filter((item): item is string => Boolean(item))
            .join(" · ")}
        </span>
        <Badge tone={finishReasonTone(meta.finishReason)}>
          {meta.finishReason ?? "recorded"}
        </Badge>
        {action}
      </header>

      {calls.length > 0 ? (
        <div className="chat-tool-flow">
          {calls.map((call, index) => (
            <ToolCallCard
              key={call.id}
              call={call}
              result={toolResults.get(call.id)?.meta ?? null}
              index={index}
              selected={selectedTraceId === call.id}
              onSelect={onSelectTrace}
            />
          ))}
        </div>
      ) : null}

      {body}

      {meta.error ? (
        <div className="chat-turn__error" role="status">
          <Icon name="info" size={15} />
          <div>
            <strong>{meta.error.code}</strong>
            <p>{meta.error.detail}</p>
          </div>
        </div>
      ) : null}

      {citations.length > 0 ? (
        <div className="citations-row chat-turn__citations">
          {citations.map((token) => (
            <CitationChip
              key={`${token.kind}:${token.id}:${token.chunk ?? ""}`}
              token={token}
              onOpen={onOpenCitation}
            />
          ))}
        </div>
      ) : null}

      {usage.length > 0 ? (
        <dl className="chat-turn__usage">
          {usage.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{formatNumber(row.value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}
