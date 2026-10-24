import { useMemo } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { formatNumber } from "../../../lib/format";
import { formatArgumentValue } from "../../chat/format";
import { MarkdownBody } from "../../chat/component/MarkdownBody";
import { toolStatusTone } from "../../chat/component/status";
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

function formatDuration(value: number | null): string | null {
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
  return (
    <section className="pi-inspector__preserved">
      <header className="pi-inspector__preserved-head">
        <div>
          <p className="eyebrow">Still on the desk</p>
          <strong>Last viewed resource</strong>
          <code>
            {target.type}:{target.id}
            {target.chunk !== null ? ` · chunk ${target.chunk}` : ""}
          </code>
        </div>
        <PanelLink to={viewerHref(target)}>
          {target.type === "file" ? "Open file" : "Open memory"}
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
  if (item.kind === "assistant" && item.text) {
    return (
      <article className="pi-inspector__assistant">
        <p className="eyebrow">Recorded prose · composing</p>
        <MarkdownBody markdown={item.text} />
      </article>
    );
  }
  if (item.kind === "orienting") {
    return (
      <PanelEmpty
        icon="layers"
        title="Orienting"
        detail="The run has opened and the model is choosing its first operation. No hidden reasoning is shown here."
      />
    );
  }
  return <InspectorPanel item={item} />;
}

function TraceMeta({ item }: { readonly item: TraceItem }) {
  const duration = formatDuration(item.durationMs);
  const argumentsList = item.arguments ? Object.entries(item.arguments) : [];

  return (
    <>
      <div className="pi-inspector__meta">
        <Badge tone={toolStatusTone(item.status)}>{item.status}</Badge>
        {item.step !== null ? <span>step {item.step}</span> : null}
        {duration ? <span>{duration}</span> : null}
        {item.entryId !== null ? <span>entry #{item.entryId}</span> : null}
        {item.errorCode ? (
          <span className="pi-inspector__error-code">{item.errorCode}</span>
        ) : null}
      </div>

      {argumentsList.length > 0 ? (
        <details className="pi-inspector__args">
          <summary>Tool arguments</summary>
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
    <aside className="pi-inspector" aria-label="Agent workbench">
      <header className="pi-inspector__head">
        <div>
          <p className="eyebrow">Workbench · {following ? "live follow" : "pinned"}</p>
          <h2>{item ? traceLabel(item) : "No work yet"}</h2>
          {item ? (
            <p className="pi-inspector__phase">
              <span className={`pi-phase-dot pi-phase-dot--${phaseForItem(item)}`} aria-hidden="true" />
              {phaseLabel(phaseForItem(item))}
              {item.live ? " · live" : " · recorded"}
            </p>
          ) : (
            <p className="pi-inspector__phase">The bench waits for the first operation.</p>
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
          Follow current
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
                  ? "Auto-following the newest recorded tool. Click a trace row to pin it."
                  : "Pinned. Later tool calls will not steal this view."}
              </span>
              {!following ? (
                <button type="button" onClick={onFollow}>
                  Return to live
                </button>
              ) : null}
            </footer>
          </>
        ) : (
          <div className="pi-inspector__empty">
            <span className="pi-inspector__empty-mark" aria-hidden="true">
              <Icon name="layers" size={22} />
            </span>
            <h3>A clean bench</h3>
            <p>
              Send a note in this thread. Every recorded search, read,
              comparison, save, and presentation appears here with its real
              preview and resource.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
