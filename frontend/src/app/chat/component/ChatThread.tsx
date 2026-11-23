import { memo, useMemo } from "react";

import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  assistantText,
  readToolResultInfo,
  readUserAttachments,
  userText,
  type CitationToken,
  type ResourceMeta,
  type ToolResultInfo,
} from "../types";
import { buildTimeline } from "../timeline";
import { PageContextCard } from "../../agent/component/PageContextCard";
import { isPageContextEntry } from "../../agent/page-context";
import { AssistantEntry } from "./AssistantEntry";
import { ContextBoundaryCard } from "./ContextBoundaryCard";
import { NoticeEntry } from "./NoticeEntry";
import { ToolResultCard } from "./ToolResultCard";
import { UserMarginalia } from "./UserMarginalia";

const HIDDEN_KINDS = new Set(["pi.system"]);

interface ChatThreadProps {
  readonly entries: readonly AgentEntrySchema[];
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly onForkEntry?: (entryId: number) => void;
  readonly forkingEntryId?: number | null;
  readonly forkDisabled?: boolean;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
  readonly highlightedEntryId?: number | null;
}

function ForkEntryAction({
  entryId,
  disabled,
  forking,
  onFork,
}: {
  readonly entryId: number;
  readonly disabled: boolean;
  readonly forking: boolean;
  readonly onFork: (entryId: number) => void;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className="chat-entry__fork"
      onClick={() => onFork(entryId)}
      disabled={disabled}
      title={
        disabled
          ? t("chat.thread.forkDisabled")
          : t("chat.thread.forkHere")
      }
      aria-label={t("chat.thread.forkAria", { entryId })}
      aria-busy={forking || undefined}
    >
      <Icon name="branch" size={11} />
      {forking ? t("chat.thread.forking") : t("chat.thread.fork")}
    </button>
  );
}

function CopyEntryAction({ value }: { readonly value: string }) {
  const { t } = useI18n();
  if (value.trim().length === 0) {
    return null;
  }
  return (
    <CopyButton
      value={value}
      iconOnly
      label={t("chat.thread.copyMessage")}
      title={t("chat.thread.copyMessageTitle")}
      className="chat-entry__copy"
    />
  );
}

function entryCopyValue(entry: AgentEntrySchema): string {
  if (entry.kind === "pi.user") {
    return userText(entry);
  }
  if (entry.kind === "pi.assistant") {
    return assistantText(entry);
  }
  return "";
}

function ThreadEntry({
  entry,
  toolResults,
  memoryTitles,
  onForkEntry,
  forkingEntryId,
  forkDisabled,
  selectedTraceId,
  onSelectTrace,
  onOpenCitation,
  onOpenResource,
}: {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly onForkEntry?: (entryId: number) => void;
  readonly forkingEntryId?: number | null;
  readonly forkDisabled?: boolean;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}) {
  if (isPageContextEntry(entry)) {
    return <PageContextCard entry={entry} />;
  }
  const forkAction =
    onForkEntry && (entry.kind === "pi.user" || entry.kind === "pi.assistant") ? (
      <ForkEntryAction
        entryId={entry.id}
        disabled={forkDisabled === true || forkingEntryId === entry.id}
        forking={forkingEntryId === entry.id}
        onFork={onForkEntry}
      />
    ) : null;
  const copyValue = entryCopyValue(entry);
  const headerAction = forkAction ? (
    <span className="chat-entry__actions">{forkAction}</span>
  ) : null;
  const copyAction =
    copyValue.trim().length > 0 ? <CopyEntryAction value={copyValue} /> : null;
  switch (entry.kind) {
    case "pi.user":
      return (
        <UserMarginalia
          text={userText(entry)}
          attachments={readUserAttachments(entry)}
          createdAt={entry.created_at}
          action={headerAction}
          copyAction={copyAction}
        />
      );
    case "pi.assistant":
      return (
        <AssistantEntry
          entry={entry}
          toolResults={toolResults}
          memoryTitles={memoryTitles}
          action={headerAction}
          copyAction={copyAction}
          selectedTraceId={selectedTraceId}
          onSelectTrace={onSelectTrace}
          onOpenCitation={onOpenCitation}
        />
      );
    case "pi.tool-result":
      return (
        <ToolResultCard
          entry={entry}
          selectedTraceId={selectedTraceId}
          onSelectTrace={onSelectTrace}
          onOpenResource={onOpenResource}
        />
      );
    case "pi.compaction":
    case "pi.reset":
      return <ContextBoundaryCard entry={entry} />;
    case "ui.notice":
      return <NoticeEntry entry={entry} />;
    default:
      return null;
  }
}

function entryClassName(highlighted: boolean): string {
  return highlighted ? "chat-entry is-highlighted" : "chat-entry";
}

/** The reading view for one transcript: turns, tool steps, and context boundaries. */
export const ChatThread = memo(function ChatThread({
  entries,
  memoryTitles,
  onForkEntry,
  forkingEntryId = null,
  forkDisabled = false,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
  onOpenResource,
  highlightedEntryId = null,
}: ChatThreadProps) {
  const toolResults = useMemo(() => {
    const result = new Map<string, ToolResultInfo>();
    for (const entry of entries) {
      if (entry.kind !== "pi.tool-result") {
        continue;
      }
      const info = readToolResultInfo(entry);
      if (info.callId) {
        result.set(info.callId, info);
      }
    }
    return result;
  }, [entries]);

  // Every assistant step and its immediately following tool results stay in
  // transcript order. Nothing linked is folded out of the reading view.
  const timeline = useMemo(() => buildTimeline(entries), [entries]);

  return (
    <div className="chat-thread">
      <div className="chat-thread__list">
        {timeline.map((item) => {
          if (item.kind === "entry") {
            if (HIDDEN_KINDS.has(item.entry.kind)) {
              return null;
            }
            return (
              <div
                className={entryClassName(item.entry.id === highlightedEntryId)}
                id={`entry-${item.entry.id}`}
                key={item.entry.id}
              >
                <ThreadEntry
                  entry={item.entry}
                  toolResults={toolResults}
                  memoryTitles={memoryTitles}
                  onForkEntry={onForkEntry}
                  forkingEntryId={forkingEntryId}
                  forkDisabled={forkDisabled}
                  selectedTraceId={selectedTraceId}
                  onSelectTrace={onSelectTrace}
                  onOpenCitation={onOpenCitation}
                  onOpenResource={onOpenResource}
                />
              </div>
            );
          }

          const forkAction =
            onForkEntry !== undefined ? (
              <ForkEntryAction
                entryId={item.entry.id}
                disabled={
                  forkDisabled === true || forkingEntryId === item.entry.id
                }
                forking={forkingEntryId === item.entry.id}
                onFork={onForkEntry}
              />
            ) : null;
          const copyValue = item.text;
          const headerAction = forkAction ? (
            <span className="chat-entry__actions">{forkAction}</span>
          ) : null;
          const copyAction =
            copyValue.trim().length > 0 ? (
              <CopyEntryAction value={copyValue} />
            ) : null;

          return (
            <div className="chat-timeline__turn" key={`assistant-${item.entry.id}`}>
              <div
                className={entryClassName(item.entry.id === highlightedEntryId)}
                id={`entry-${item.entry.id}`}
              >
                <AssistantEntry
                  entry={item.entry}
                  toolResults={toolResults}
                  memoryTitles={memoryTitles}
                  action={headerAction}
                  copyAction={copyAction}
                  hasToolStep={item.results.length > 0}
                  selectedTraceId={selectedTraceId}
                  onSelectTrace={onSelectTrace}
                  onOpenCitation={onOpenCitation}
                />
              </div>
              {item.results.map((result) => (
                <div
                  className={entryClassName(
                    result.entry.id === highlightedEntryId,
                  )}
                  id={`entry-${result.entry.id}`}
                  key={result.entry.id}
                >
                  <ToolResultCard
                    entry={result.entry}
                    step={item.step}
                    selectedTraceId={selectedTraceId}
                    onSelectTrace={onSelectTrace}
                    onOpenResource={onOpenResource}
                  />
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
});
