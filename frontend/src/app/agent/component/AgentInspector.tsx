import { useMemo } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { formatArgumentValue } from "../../chat/format";
import { MarkdownBody } from "../../chat/component/MarkdownBody";
import { toolStatusLabel, toolStatusTone } from "../../chat/component/status";
import {
  currentTraceIndex,
  itemResourceTarget,
  phaseForItem,
  phaseLabel,
  traceLabel,
  viewerHref,
  type ResourceTarget,
  type TraceItem,
} from "../trace";
import { InspectorPanel } from "./inspector/InspectorPanels";
import {
  InspectorFileStage,
  InspectorMemoryStage,
  PanelEmpty,
  PanelLink,
} from "./inspector/common";

interface AgentInspectorProps {
  readonly items: readonly TraceItem[];
  readonly pinnedId: string | null;
  readonly onFollow: () => void;
}

function formatDuration(
  value: number | null,
  formatNumber: (value: number) => string,
): string | null {
  if (value === null) {
    return null;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)} s`;
  }
  return `${formatNumber(value)} ms`;
}

function preservedTargetFor(
  items: readonly TraceItem[],
  index: number,
): ResourceTarget | null {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const target = itemResourceTarget(items[cursor]);
    if (target) {
      return target;
    }
  }
  return null;
}

function PreservedResource({ target }: { readonly target: ResourceTarget }) {
  const { t } = useI18n();
  return (
    <section className="pi-inspector__preserved">
      <header className="pi-inspector__preserved-head">
        <div>
          <p className="eyebrow">{t("chat.workbench.stillOnDesk")}</p>
          <strong>{t("chat.workbench.lastViewed")}</strong>
          <code>
            {target.type}:{target.id}
            {target.chunk !== null
              ? ` · ${t("chat.common.chunk", { chunk: target.chunk })}`
              : ""}
          </code>
        </div>
        <PanelLink to={viewerHref(target)}>
          {target.type === "file"
            ? t("chat.workbench.openFile")
            : t("chat.workbench.openMemory")}
        </PanelLink>
      </header>
      {target.type === "file" ? (
        <InspectorFileStage fileId={target.id} chunk={target.chunk} />
      ) : null}
      {target.type === "memory" ? <InspectorMemoryStage memoryId={target.id} /> : null}
    </section>
  );
}

function TraceBody({ item }: { readonly item: TraceItem }) {
  const { t } = useI18n();
  if (item.kind === "assistant" && item.text) {
    return (
      <article className="pi-inspector__assistant">
        <p className="eyebrow">{t("chat.workbench.composingEyebrow")}</p>
        <MarkdownBody markdown={item.text} />
      </article>
    );
  }
  if (item.kind === "orienting") {
    return (
      <PanelEmpty
        icon="layers"
        title={t("chat.workbench.orientingTitle")}
        detail={t("chat.workbench.orientingDetail")}
      />
    );
  }
  return <InspectorPanel item={item} />;
}

function TraceMeta({ item }: { readonly item: TraceItem }) {
  const { t, formatNumber } = useI18n();
  const duration = formatDuration(item.durationMs, formatNumber);
  const argumentsList = item.arguments ? Object.entries(item.arguments) : [];
  const statusLabel = toolStatusLabel(item.status, t, item.status);

  return (
    <>
      <div className="pi-inspector__meta">
        <Badge tone={toolStatusTone(item.status)}>{statusLabel}</Badge>
        {item.step !== null ? (
          <span>{t("chat.workbench.step", { step: item.step })}</span>
        ) : null}
        {duration ? <span>{duration}</span> : null}
        {item.entryId !== null ? (
          <span>{t("chat.workbench.entry", { id: item.entryId })}</span>
        ) : null}
        {item.errorCode ? (
          <span className="pi-inspector__error-code">{item.errorCode}</span>
        ) : null}
      </div>

      {argumentsList.length > 0 ? (
        <details className="pi-inspector__args">
          <summary>{t("chat.workbench.toolArguments")}</summary>
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
    </>
  );
}

/**
 * The expanded workspace workbench.
 *
 * Auto-follow selects the newest trace item until the keeper pins something.
 * A pinned item is never stolen by later tool calls, and the last resource-
 * bearing item stays mounted under panels that have no resource of their own.
 */
export function AgentInspector({
  items,
  pinnedId,
  onFollow,
}: AgentInspectorProps) {
  const { t } = useI18n();
  const pinnedIndex = useMemo(
    () => (pinnedId === null ? -1 : items.findIndex((item) => item.id === pinnedId)),
    [items, pinnedId],
  );
  const autoIndex = currentTraceIndex(items);
  const index = pinnedIndex >= 0 ? pinnedIndex : autoIndex;
  const item = index >= 0 ? items[index] : null;
  const following = pinnedIndex < 0;
  const target = item ? itemResourceTarget(item) : null;
  const preserved = item && !target ? preservedTargetFor(items, index) : null;

  return (
    <aside className="pi-inspector" aria-label={t("chat.workbench.aria")}>
      <header className="pi-inspector__head">
        <div>
          <p className="eyebrow">
            {following
              ? t("chat.workbench.eyebrowLive")
              : t("chat.workbench.eyebrowPinned")}
          </p>
          <h2>{item ? traceLabel(item) : t("chat.workbench.noWork")}</h2>
          {item ? (
            <p className="pi-inspector__phase">
              <span className={`pi-phase-dot pi-phase-dot--${phaseForItem(item)}`} aria-hidden="true" />
              {phaseLabel(phaseForItem(item))}
              {item.live
                ? t("chat.workbench.live")
                : t("chat.workbench.recorded")}
            </p>
          ) : (
            <p className="pi-inspector__phase">{t("chat.workbench.waiting")}</p>
          )}
        </div>
        <Button
          variant={following ? "secondary" : "ink"}
          size="sm"
          onClick={onFollow}
          aria-pressed={following}
          className="pi-inspector__follow"
        >
          <Icon name="timeline" size={14} />
          {t("chat.workbench.follow")}
        </Button>
      </header>

      <div className="pi-inspector__scroll">
        {item ? (
          <>
            <TraceMeta item={item} />
            <TraceBody item={item} />
            {preserved ? <PreservedResource target={preserved} /> : null}
            <footer className="pi-inspector__foot">
              <span>
                {following
                  ? t("chat.workbench.autoFollow")
                  : t("chat.workbench.pinnedNote")}
              </span>
              {!following ? (
                <button type="button" onClick={onFollow}>
                  {t("chat.workbench.returnLive")}
                </button>
              ) : null}
            </footer>
          </>
        ) : (
          <div className="pi-inspector__empty">
            <span className="pi-inspector__empty-mark" aria-hidden="true">
              <Icon name="layers" size={22} />
            </span>
            <h3>{t("chat.workbench.clean")}</h3>
            <p>{t("chat.workbench.cleanDetail")}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
