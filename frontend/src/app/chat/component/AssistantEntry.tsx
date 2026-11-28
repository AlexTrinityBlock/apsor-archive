import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n, type TranslationKey } from "../../i18n";
import {
  assistantText,
  readAssistantMeta,
  readToolCalls,
  type CitationToken,
  type ToolResultInfo,
} from "../types";
import { MarkdownBody } from "./MarkdownBody";
import { ThinkingBlock } from "./ThinkingBlock";
import { ToolCallCard } from "./ToolCallCard";
import { finishReasonTone } from "./status";

interface AssistantEntryProps {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly action?: ReactNode;
  readonly copyAction?: ReactNode;
  /** A linked result entry is rendered right after this step. */
  readonly hasToolStep?: boolean;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
}

type UsageKey =
  | "prompt"
  | "completion"
  | "total"
  | "reasoning"
  | "cacheHit"
  | "cacheMiss";

function usageRows(
  usage: Readonly<Record<string, number>>,
): ReadonlyArray<{ key: UsageKey; value: number }> {
  const rows: Array<{ key: UsageKey; value: number }> = [
    { key: "prompt", value: usage.prompt_tokens ?? 0 },
    { key: "completion", value: usage.completion_tokens ?? 0 },
    { key: "total", value: usage.total_tokens ?? 0 },
    { key: "reasoning", value: usage.reasoning_tokens ?? 0 },
    { key: "cacheHit", value: usage.prompt_cache_hit_tokens ?? 0 },
    { key: "cacheMiss", value: usage.prompt_cache_miss_tokens ?? 0 },
  ];
  return rows.filter((row) => row.value > 0);
}

const USAGE_LABEL_KEYS: Readonly<Record<UsageKey, TranslationKey>> = {
  prompt: "chat.assistant.usagePrompt",
  completion: "chat.assistant.usageCompletion",
  total: "chat.assistant.usageTotal",
  reasoning: "chat.assistant.usageReasoning",
  cacheHit: "chat.assistant.usageCacheHit",
  cacheMiss: "chat.assistant.usageCacheMiss",
};

/** An archival assistant step: pending tool chips, prose, citations, and usage. */
export function AssistantEntry({
  entry,
  toolResults,
  memoryTitles,
  action,
  copyAction,
  hasToolStep = false,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
}: AssistantEntryProps) {
  const { t, formatNumber } = useI18n();
  const meta = readAssistantMeta(entry);
  const text = assistantText(entry);
  const calls = readToolCalls(entry);
  const usage = usageRows(meta.usage);
  // A call whose result entry is in the transcript is rendered by that entry.
  // Only a call that never produced one keeps a compact waiting chip here.
  const pendingCalls = calls.filter((call) => !toolResults.has(call.id));

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
  } else if (pendingCalls.length === 0 && !hasToolStep && !meta.error) {
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
        <span>{t("chat.assistant.author")}</span>
        <span className="chat-turn__meta">
          {[meta.provider, meta.model]
            .filter((item): item is string => Boolean(item))
            .join(" · ")}
        </span>
        {meta.step === null ? null : (
          <span className="chat-turn__step">
            {t("chat.timeline.step", { step: meta.step })}
          </span>
        )}
        <Badge tone={finishReasonTone(meta.finishReason)}>
          {meta.finishReason ?? t("chat.common.recorded")}
        </Badge>
        {action}
      </header>

      {pendingCalls.length > 0 ? (
        <div className="chat-tool-flow">
          {pendingCalls.map((call, index) => (
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

      <ThinkingBlock text={meta.reasoning} tokens={meta.reasoningTokens} />

      {body}

      {copyAction ? (
        <div className="chat-turn__copy">{copyAction}</div>
      ) : null}

      {meta.error ? (
        <div className="chat-turn__error" role="status">
          <Icon name="info" size={15} />
          <div>
            <strong>{meta.error.code}</strong>
            <p>{meta.error.detail}</p>
          </div>
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
