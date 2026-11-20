import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n, type TranslationKey } from "../../i18n";
import { readPlotSpec } from "../plot";
import {
  assistantText,
  parseCitationLabel,
  readAssistantMeta,
  readToolCalls,
  type CitationToken,
  type ResourceMeta,
  type ToolResultInfo,
} from "../types";
import { CitationChip } from "./CitationChip";
import { MarkdownBody } from "./MarkdownBody";
import { PlotBlock } from "./PlotBlock";
import { ResourceCard } from "./ResourceCard";
import { ToolCallCard } from "./ToolCallCard";
import { ToolDiagnostics, type ToolDiagnosticItem } from "./ToolDiagnostics";
import { finishReasonTone, isToolFailure } from "./status";

interface AssistantEntryProps {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly action?: ReactNode;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}

type UsageKey = "prompt" | "completion" | "total" | "cacheHit" | "cacheMiss";

function usageRows(
  usage: Readonly<Record<string, number>>,
): ReadonlyArray<{ key: UsageKey; value: number }> {
  const rows: Array<{ key: UsageKey; value: number }> = [
    { key: "prompt", value: usage.prompt_tokens ?? 0 },
    { key: "completion", value: usage.completion_tokens ?? 0 },
    { key: "total", value: usage.total_tokens ?? 0 },
    { key: "cacheHit", value: usage.prompt_cache_hit_tokens ?? 0 },
    { key: "cacheMiss", value: usage.prompt_cache_miss_tokens ?? 0 },
  ];
  return rows.filter((row) => row.value > 0);
}

const USAGE_LABEL_KEYS: Readonly<Record<UsageKey, TranslationKey>> = {
  prompt: "chat.assistant.usagePrompt",
  completion: "chat.assistant.usageCompletion",
  total: "chat.assistant.usageTotal",
  cacheHit: "chat.assistant.usageCacheHit",
  cacheMiss: "chat.assistant.usageCacheMiss",
};

/** An archival assistant turn: tool step chips, prose, citations, and usage. */
export function AssistantEntry({
  entry,
  toolResults,
  memoryTitles,
  action,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
  onOpenResource,
}: AssistantEntryProps) {
  const { t, formatNumber } = useI18n();
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
  const failures: ToolDiagnosticItem[] = [];
  const visibleCalls = calls.filter((call) => {
    const result = toolResults.get(call.id)?.meta ?? null;
    if (!isToolFailure(result?.status)) {
      return true;
    }
    failures.push({
      id: call.id,
      name: call.name,
      status: result?.status ?? null,
      errorCode: result?.errorCode ?? null,
      detail: result?.detail ?? null,
    });
    return false;
  });
  const plots = visibleCalls.flatMap((call) => {
    const plotData = toolResults.get(call.id)?.meta.data;
    return plotData !== null &&
      plotData !== undefined &&
      readPlotSpec(plotData) !== null
      ? [{ id: call.id, data: plotData }]
      : [];
  });
  // A presented resource stays visible in the transcript even though its raw
  // tool result is folded into the assistant turn. Deduplicate by target so a
  // repeated presentation does not stack identical bubbles.
  const resources: ResourceMeta[] = [];
  const seenResources = new Set<string>();
  for (const call of visibleCalls) {
    const resource = toolResults.get(call.id)?.meta.resource ?? null;
    if (resource === null) {
      continue;
    }
    const key = `${resource.resourceType}:${resource.resourceId ?? "none"}:${
      resource.chunk ?? ""
    }`;
    if (seenResources.has(key)) {
      continue;
    }
    seenResources.add(key);
    resources.push(resource);
  }

  let body: ReactNode = null;
  if (text.length > 0) {
    body = (
      <div className="chat-turn__bubble">
        <MarkdownBody
          markdown={text}
          memoryTitles={memoryTitles}
          onOpenCitation={onOpenCitation}
        />
      </div>
    );
  } else if (visibleCalls.length === 0 && failures.length === 0 && !meta.error) {
    body = (
      <p className="chat-turn__silent">{t("chat.assistant.silent")}</p>
    );
  }

  return (
    <article className="chat-turn chat-turn--agent">
      <header className="chat-turn__author">
        <span className="chat-turn__mark chat-turn__mark--agent" aria-hidden="true">
          <Icon name="spark" size={11} />
        </span>
        <span>Apsor Archive Agent</span>
        <span className="chat-turn__meta">
          {[
            meta.provider,
            meta.model,
            meta.step === null
              ? null
              : t("chat.assistant.step", { step: meta.step }),
          ]
            .filter((item): item is string => Boolean(item))
            .join(" · ")}
        </span>
        <Badge tone={finishReasonTone(meta.finishReason)}>
          {meta.finishReason ?? t("chat.common.recorded")}
        </Badge>
        {action}
      </header>

      {visibleCalls.length > 0 ? (
        <div className="chat-tool-flow">
          {visibleCalls.map((call, index) => (
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

      {resources.length > 0 ? (
        <div className="chat-resource-stack">
          {resources.map((resource) => (
            <ResourceCard
              key={`${resource.resourceType}:${resource.resourceId ?? "none"}:${
                resource.chunk ?? ""
              }`}
              resource={resource}
              onOpen={onOpenResource}
            />
          ))}
        </div>
      ) : null}

      {plots.map((plot) => (
        <PlotBlock key={plot.id} data={plot.data} />
      ))}

      <ToolDiagnostics items={failures} />

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
              memoryTitle={
                token.kind === "memory"
                  ? memoryTitles?.get(token.id)
                  : undefined
              }
              onOpen={onOpenCitation}
            />
          ))}
        </div>
      ) : null}

      {usage.length > 0 ? (
        <dl className="chat-turn__usage">
          {usage.map((row) => (
            <div key={row.key}>
              <dt>{t(USAGE_LABEL_KEYS[row.key])}</dt>
              <dd>{formatNumber(row.value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}
