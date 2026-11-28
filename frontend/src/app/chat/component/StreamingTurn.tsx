import { memo } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { useI18n, type Translate } from "../../i18n";
import type {
  ChatStreamTool,
  ChatStreamView,
} from "../hook/useChatStream";
import type {
  CitationToken,
  ResourceMeta,
  ToolResultMeta,
} from "../types";
import { useLiveSpeaker } from "../hook/useLiveSpeaker";
import { MarkdownBody } from "./MarkdownBody";
import { ReplyAuthor } from "./ReplyAuthor";
import { ThinkingBlock } from "./ThinkingBlock";
import { ToolStepCard } from "./ToolStepCard";
import { UserMarginalia } from "./UserMarginalia";
import { finishReasonTone } from "./status";

interface StreamingTurnProps {
  readonly stream: ChatStreamView;
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenCitation?: (token: CitationToken) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}

function pageContextLabel(stream: ChatStreamView, t: Translate): string {
  if (!stream.pageContextAttached) {
    return t("chat.streaming.pageAttached");
  }
  if (stream.pageContextEntryId === null) {
    return t("chat.streaming.pageCaptured");
  }
  return t("chat.streaming.pageCapturedEntry", {
    id: stream.pageContextEntryId,
  });
}

function asResult(tool: ChatStreamTool): ToolResultMeta {
  return {
    tool: tool.name,
    status: tool.status,
    errorCode: tool.errorCode,
    durationMs: tool.durationMs,
    arguments: tool.arguments,
    resource: tool.resource,
    data: tool.data,
    detail: null,
  };
}

interface StreamingToolStepProps {
  readonly tool: ChatStreamTool;
  readonly step: number;
  readonly selected: boolean;
  readonly onSelect?: (callId: string) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}

/**
 * One live tool step whose render is owned by the tool's own events.
 *
 * The reducer replaces only the tool object that changed, so a token delta
 * leaves this card's props untouched. Memoizing the card keeps a presented PDF
 * or chart mounted and untouched while the assistant prose streams above it.
 */
const StreamingToolStep = memo(function StreamingToolStep({
  tool,
  step,
  selected,
  onSelect,
  onOpenResource,
}: StreamingToolStepProps) {
  return (
    <ToolStepCard
      meta={asResult(tool)}
      step={step}
      entryId={tool.entryId}
      callId={tool.id}
      selected={selected}
      onSelect={onSelect}
      onOpenResource={onOpenResource}
    />
  );
});

/** The optimistic turn shown while the SSE stream is open. */
export const StreamingTurn = memo(function StreamingTurn({
  stream,
  memoryTitles,
  selectedTraceId = null,
  onSelectTrace,
  onOpenCitation,
  onOpenResource,
}: StreamingTurnProps) {
  const { t, formatNumber } = useI18n();
  const total = stream.usage.total_tokens;
  const visibleSegments = stream.segments.filter(
    (segment) =>
      segment.text.trim().length > 0 ||
      segment.toolCalls.length > 0 ||
      segment.reasoning.trim().length > 0,
  );
  const hasHistory = visibleSegments.length > 0;
  const running = stream.status === "running";
  const speaker = useLiveSpeaker();
  const lastIndex = visibleSegments.at(-1)?.index ?? null;

  return (
    <div className="chat-live-turn" aria-busy={stream.status === "running"}>
      {stream.userContent.length > 0 || stream.userAttachments.length > 0 ? (
        <UserMarginalia
          text={stream.userContent}
          attachments={stream.userAttachments}
          pending
        />
      ) : null}

      <article className="chat-turn chat-turn--agent is-live">
        <header className="chat-turn__author">
          <ReplyAuthor speaker={speaker} live={running} />
          <span className="chat-turn__meta">
            {stream.runId === null
              ? t("chat.streaming.openingRun")
              : t("chat.streaming.run", { id: stream.runId })}
          </span>
          {stream.finishReason ? (
            <Badge tone={finishReasonTone(stream.finishReason)}>
              {stream.finishReason}
            </Badge>
          ) : null}
        </header>

        {hasHistory ? (
          <div className="chat-timeline chat-timeline--live">
            {visibleSegments.map((segment) => {
              const writing =
                running &&
                segment.index === lastIndex &&
                segment.toolCalls.length === 0;
              const thinking =
                writing &&
                segment.text.trim().length === 0 &&
                segment.reasoning.trim().length > 0;
              return (
              <div className="chat-timeline__segment" key={segment.index}>
                {segment.reasoning.trim().length > 0 ||
                segment.text.trim().length > 0 ? (
                  <div className="chat-timeline__prose">
                    <p className="chat-timeline__step">
                      {t("chat.timeline.step", { step: segment.index })}
                    </p>
                    <ThinkingBlock
                      text={segment.reasoning}
                      tokens={segment.reasoningTokens}
                    />
                    {thinking ? (
                      <p className="chat-live-thinking">
                        <span className="chat-pulse" aria-hidden="true" />
                        {t("chat.streaming.thinking")}
                      </p>
                    ) : null}
                    {segment.text.trim().length > 0 ? (
                      <div
                        className={
                          writing
                            ? "chat-turn__bubble is-writing"
                            : "chat-turn__bubble"
                        }
                      >
                        <MarkdownBody
                          markdown={segment.text}
                          memoryTitles={memoryTitles}
                          onOpenCitation={onOpenCitation}
                        />
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {segment.toolCalls.length > 0 ? (
                  <div className="chat-tool-flow">
                    {segment.toolCalls.map((tool) => (
                      <StreamingToolStep
                        key={tool.id}
                        tool={tool}
                        step={segment.index}
                        selected={selectedTraceId === tool.id}
                        onSelect={onSelectTrace}
                        onOpenResource={onOpenResource}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
              );
            })}
          </div>
        ) : null}

        {stream.status === "waiting" ? (
          <p className="chat-turn__silent is-live" role="status">
            <span className="chat-pulse" aria-hidden="true" />
            {t("chat.streaming.waitingApproval")}
          </p>
        ) : null}

        {!hasHistory && stream.status !== "waiting" && !stream.error ? (
          <p className="chat-turn__silent is-live">
            <span className="chat-pulse" aria-hidden="true" />
            {t("chat.streaming.waitingFirstLine")}
          </p>
        ) : null}

        {stream.pageContextKey !== null && stream.runId !== null ? (
          <p className="chat-context-live">
            <Icon name="layers" size={12} />
            {pageContextLabel(stream, t)}
          </p>
        ) : null}

        {stream.error ? (
          <div className="chat-turn__error" role="status">
            <Icon name="info" size={15} />
            <div>
              <strong>{stream.error.code}</strong>
              <p>{stream.error.detail}</p>
            </div>
          </div>
        ) : null}

        {total !== undefined && total > 0 ? (
          <p className="chat-turn__usage-note">
            {t("chat.streaming.tokens", { count: formatNumber(total) })}
          </p>
        ) : null}
      </article>
    </div>
  );
});
