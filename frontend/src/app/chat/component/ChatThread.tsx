import { memo, useMemo } from "react";

import { Icon } from "../../component/Icon";
import type {
  AgentConversationDetailSchema,
  AgentEntrySchema,
} from "../../generated-apis-types/schemas";
import {
  readToolResultInfo,
  systemVersions,
  userText,
  type ToolResultInfo,
} from "../types";
import { PageContextCard } from "../../agent/component/PageContextCard";
import { isPageContextEntry } from "../../agent/page-context";
import { AssistantEntry } from "./AssistantEntry";
import { ContextBoundaryCard } from "./ContextBoundaryCard";
import { MethodDisclosure } from "./MethodDisclosure";
import { NoticeEntry } from "./NoticeEntry";
import { ToolResultCard } from "./ToolResultCard";
import { UserMarginalia } from "./UserMarginalia";

const HIDDEN_KINDS = new Set(["pi.system"]);

interface ChatThreadProps {
  readonly entries: readonly AgentEntrySchema[];
  readonly conversation: AgentConversationDetailSchema;
  readonly onForkEntry?: (entryId: number) => void;
  readonly forkingEntryId?: number | null;
  readonly forkDisabled?: boolean;
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
  return (
    <button
      type="button"
      className="chat-entry__fork"
      onClick={() => onFork(entryId)}
      disabled={disabled}
      title={
        disabled
          ? "Forking is unavailable while the thread is archived or busy."
          : "Fork a new thread from this entry"
      }
      aria-label={`Fork conversation from entry ${entryId}`}
      aria-busy={forking || undefined}
    >
      <Icon name="branch" size={12} />
      {forking ? "Forking…" : "Fork from here"}
    </button>
  );
}

function ThreadEntry({
  entry,
  toolResults,
  onForkEntry,
  forkingEntryId,
  forkDisabled,
}: {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
  readonly onForkEntry?: (entryId: number) => void;
  readonly forkingEntryId?: number | null;
  readonly forkDisabled?: boolean;
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
          action={forkAction}
        />
      );
    case "pi.tool-result":
      return <ToolResultCard entry={entry} />;
    case "pi.compaction":
    case "pi.reset":
      return <ContextBoundaryCard entry={entry} />;
    case "ui.notice":
      return <NoticeEntry entry={entry} />;
    default:
      return null;
  }
}

/** The reading view for one transcript: visible sheets plus a method drawer. */
export const ChatThread = memo(function ChatThread({
  entries,
  conversation,
  onForkEntry,
  forkingEntryId = null,
  forkDisabled = false,
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

  const visible = entries.filter((entry) => !HIDDEN_KINDS.has(entry.kind));
  const hiddenCount = entries.length - visible.length;

  return (
    <div className="chat-thread">
      <MethodDisclosure
        conversation={conversation}
        hiddenCount={hiddenCount}
        entryCount={conversation.entries_total}
        versions={systemVersions(entries)}
      />

      {visible.length === 0 ? (
        <div className="chat-thread__empty">
          <p className="eyebrow">A fresh sheet</p>
          <p>
            {conversation.status === "archived"
              ? "This thread is archived. Restore it to add the first note."
              : "The desk is ready. Write the first note below, and the archive will answer from its files, memories, and media."}
          </p>
        </div>
      ) : (
        <div className="chat-thread__list">
          {visible.map((entry) => (
            <div className="chat-entry" key={entry.id}>
              <ThreadEntry
                entry={entry}
                toolResults={toolResults}
                onForkEntry={onForkEntry}
                forkingEntryId={forkingEntryId}
                forkDisabled={forkDisabled}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
