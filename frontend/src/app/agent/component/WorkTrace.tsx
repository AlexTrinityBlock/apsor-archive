import { Badge } from "../../component/Badge";
import { formatNumber } from "../../../lib/format";
import { toolStatusTone } from "../../chat/component/status";
import {
  currentTraceIndex,
  phaseForItem,
  phaseLabel,
  traceLabel,
  type TerminalTrace,
  type TraceItem,
} from "../trace";

interface WorkTraceProps {
  readonly items: readonly TraceItem[];
  readonly terminal: TerminalTrace | null;
  readonly pinnedId: string | null;
  readonly onPin: (id: string) => void;
  readonly streaming: boolean;
}

function durationLabel(value: number | null): string | null {
  if (value === null) {
    return null;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)} s`;
  }
  return `${formatNumber(value)} ms`;
}

function traceSuffix(terminal: TerminalTrace | null, streaming: boolean): string {
  if (terminal) {
    return ` · ${terminal.phase}`;
  }
  if (streaming) {
    return " · running";
  }
  return "";
}

function TraceRow({
  item,
  index,
  pinned,
  current,
  onPin,
}: {
  readonly item: TraceItem;
  readonly index: number;
  readonly pinned: boolean;
  readonly current: boolean;
  readonly onPin: (id: string) => void;
}) {
  const phase = phaseForItem(item);
  const duration = durationLabel(item.durationMs);

  return (
    <li>
      <button
        type="button"
        className={[
          "pi-trace__row",
          pinned ? "is-pinned" : null,
          current ? "is-current" : null,
          item.live ? "is-live" : null,
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => onPin(item.id)}
        aria-pressed={pinned}
        title={`Pin ${traceLabel(item)} in the workbench`}
      >
        <span className="pi-trace__step" aria-hidden="true">
          {item.step === null ? "••" : String(item.step).padStart(2, "0")}
        </span>
        <span className={`pi-phase-dot pi-phase-dot--${phase}`} aria-hidden="true" />
        <span className="pi-trace__copy">
          <span className="pi-trace__label">{traceLabel(item)}</span>
          <span className="pi-trace__phase">{phaseLabel(phase)}</span>
        </span>
        {duration ? <span className="pi-trace__duration">{duration}</span> : null}
        <Badge tone={toolStatusTone(item.status)} className="pi-trace__status">
          {item.status}
        </Badge>
        <span className="pi-trace__pin" aria-hidden="true">
          {pinned ? "pinned" : index + 1}
        </span>
      </button>
    </li>
  );
}

/**
 * A recorded field sequence, not hidden chain-of-thought.
 *
 * Rows are real tool calls and assistant turns; clicking pins the workbench so
 * later calls cannot pull the inspector away.
 */
export function WorkTrace({
  items,
  terminal,
  pinnedId,
  onPin,
  streaming,
}: WorkTraceProps) {
  const latestId = items[currentTraceIndex(items)]?.id ?? null;

  return (
    <details className="pi-trace" open>
      <summary className="pi-trace__summary">
        <span className="pi-trace__title">
          <span className="eyebrow">Field sequence</span>
          <span>
            {items.length} operation{items.length === 1 ? "" : "s"}
            {traceSuffix(terminal, streaming)}
          </span>
        </span>
        <span className="pi-trace__hint">Click a row to pin the workbench</span>
      </summary>

      <div className="pi-trace__body">
        {items.length === 0 && !terminal ? (
          <p className="pi-trace__empty">
            No operations have been recorded for this turn yet.
          </p>
        ) : (
          <ol className="pi-trace__list">
            {items.map((item, index) => (
              <TraceRow
                key={item.id}
                item={item}
                index={index}
                pinned={pinnedId === item.id}
                current={pinnedId === null && latestId === item.id}
                onPin={onPin}
              />
            ))}
          </ol>
        )}

        {terminal ? (
          <div className={`pi-trace__terminal pi-trace__terminal--${terminal.phase}`}>
            <span className="pi-phase-dot" aria-hidden="true" />
            <span>{phaseLabel(terminal.phase)}</span>
            <span>{terminal.status}</span>
            {terminal.detail ? <p>{terminal.detail}</p> : null}
          </div>
        ) : null}
      </div>
    </details>
  );
}
