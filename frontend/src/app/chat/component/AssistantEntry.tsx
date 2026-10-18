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
  type ToolResultInfo,
} from "../types";
import { CitationChip } from "./CitationChip";
import { MarkdownBody } from "./MarkdownBody";
import { ToolCallCard } from "./ToolCallCard";
import { finishReasonTone } from "./status";

interface AssistantEntryProps {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
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

/** An archive sheet: Markdown prose, tool steps, citations, and usage. */
export function AssistantEntry({ entry, toolResults }: AssistantEntryProps) {
  const meta = readAssistantMeta(entry);
  const text = assistantText(entry);
  const calls = readToolCalls(entry);
  const citations: Array<NonNullable<ReturnType<typeof parseCitationLabel>>> = [];
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
  const isStep = calls.length > 0;

  let body: ReactNode = null;
  if (text.length > 0) {
    body = <MarkdownBody markdown={text} />;
  } else if (isStep) {
    body = (
      <p className="chat-sheet__silent">
        Consulted {calls.length} {calls.length === 1 ? "tool" : "tools"} before
        answering.
      </p>
    );
  } else if (!meta.error) {
    body = <p className="chat-sheet__silent">No prose was recorded for this step.</p>;
  }

  return (
    <article className={isStep ? "chat-sheet chat-sheet--step" : "chat-sheet"}>
      <header className="chat-sheet__head">
        <div className="chat-sheet__heading">
          <p className="eyebrow">
            {isStep ? "Working sheet" : "Archive sheet"} · entry {entry.id}
          </p>
          <p className="chat-sheet__model">
            {[meta.provider, meta.model, meta.step === null ? null : `step ${meta.step}`]
              .filter((item): item is string => Boolean(item))
              .join(" · ")}
          </p>
        </div>
        <Badge tone={finishReasonTone(meta.finishReason)}>
          {meta.finishReason ?? "recorded"}
        </Badge>
      </header>

      {body}

      {calls.length > 0 ? (
        <div className="chat-sheet__calls">
          {calls.map((call, index) => (
            <ToolCallCard
              key={call.id}
              call={call}
              result={toolResults.get(call.id)?.meta ?? null}
              index={index}
            />
          ))}
        </div>
      ) : null}

      {meta.error ? (
        <div className="chat-sheet__error" role="status">
          <Icon name="info" size={16} />
          <div>
            <strong>{meta.error.code}</strong>
            <p>{meta.error.detail}</p>
          </div>
        </div>
      ) : null}

      {citations.length > 0 || usage.length > 0 ? (
        <footer className="chat-sheet__foot">
          {citations.length > 0 ? (
            <div className="chat-sheet__citations">
              <span className="chat-sheet__foot-label">Sources</span>
              {citations.map((token) => (
                <CitationChip key={`${token.kind}:${token.id}`} token={token} />
              ))}
            </div>
          ) : null}
          {usage.length > 0 ? (
            <dl className="chat-sheet__usage">
              {usage.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{formatNumber(row.value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </footer>
      ) : null}
    </article>
  );
}
