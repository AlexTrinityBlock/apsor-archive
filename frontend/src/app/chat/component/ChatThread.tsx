import { memo, useMemo } from "react";

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
import { MethodDisclosure } from "./MethodDisclosure";
import { NoticeEntry } from "./NoticeEntry";
import { ToolResultCard } from "./ToolResultCard";
import { UserMarginalia } from "./UserMarginalia";

const HIDDEN_KINDS = new Set(["pi.system", "pi.reset", "pi.compaction"]);

interface ChatThreadProps {
  readonly entries: readonly AgentEntrySchema[];
  readonly conversation: AgentConversationDetailSchema;
}

function ThreadEntry({
  entry,
  toolResults,
}: {
  readonly entry: AgentEntrySchema;
  readonly toolResults: ReadonlyMap<string, ToolResultInfo>;
}) {
  if (isPageContextEntry(entry)) {
    return <PageContextCard entry={entry} />;
  }
  switch (entry.kind) {
    case "pi.user":
      return <UserMarginalia text={userText(entry)} createdAt={entry.created_at} />;
    case "pi.assistant":
      return <AssistantEntry entry={entry} toolResults={toolResults} />;
    case "pi.tool-result":
      return <ToolResultCard entry={entry} />;
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
              <ThreadEntry entry={entry} toolResults={toolResults} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
