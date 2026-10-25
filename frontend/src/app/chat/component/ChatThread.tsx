import { memo, useMemo } from "react";

import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  readToolCalls,
  readToolResultCallId,
  readToolResultInfo,
  userText,
  type CitationToken,
  type ResourceMeta,
  type ToolResultInfo,
} from "../types";
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
  switch (entry.kind) {
    case "pi.user":
      return (
        <UserMarginalia
          text={userText(entry)}
          createdAt={entry.created_at}
          action={forkAction}
        />
      );
    case "pi.assistant":
      return (
        <AssistantEntry
          entry={entry}
          toolResults={toolResults}
          memoryTitles={memoryTitles}
          action={forkAction}
          selectedTraceId={selectedTraceId}
          onSelectTrace={onSelectTrace}
          onOpenCitation={onOpenCitation}
        />
      );
    case "pi.tool-result":
      return (
        <ToolResultCard entry={entry} onOpenResource={onOpenResource} />
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

/** The reading view for one transcript: turns, tool steps, and the method drawer. */
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

  // Linked results are already rendered inside their assistant tool chips.
  const linkedResultIds = useMemo(() => {
    const ids = new Set<number>();
    for (const entry of entries) {
      if (entry.kind !== "pi.assistant") {
        continue;
      }
      for (const call of readToolCalls(entry)) {
        if (call.id.length === 0) {
          continue;
        }
        for (const resultEntry of entries) {
          if (
            resultEntry.kind === "pi.tool-result" &&
            readToolResultCallId(resultEntry) === call.id
          ) {
            ids.add(resultEntry.id);
          }
        }
      }
    }
    return ids;
  }, [entries]);

  const visible = entries.filter(
    (entry) => !HIDDEN_KINDS.has(entry.kind) && !linkedResultIds.has(entry.id),
  );

  return (
    <div className="chat-thread">
      <div className="chat-thread__list">
        {visible.map((entry) => (
          <div className="chat-entry" key={entry.id}>
            <ThreadEntry
              entry={entry}
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
        ))}
      </div>
    </div>
  );
});
