import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";

interface TimelineHeaderProps {
  readonly rangeLabel: string;
  readonly isFetching: boolean;
}

/** Timeline masthead with the real API range and the memory-recording entry point. */
export function TimelineHeader({ rangeLabel, isFetching }: TimelineHeaderProps) {
  return (
    <header className="timeline-header">
      <div className="timeline-header__copy">
        <div className="timeline-header__kicker">
          <span className="shell-tag">Temporal Density // 03</span>
          <span className="timeline-header__mono">
            Continuous chronological spine {"\u00b7"} windowed reads
          </span>
        </div>
        <h1 className="page-title">Sparse Timeline &amp; Tree-Ring Chronology</h1>
        <p className="page-desc timeline-header__subtitle">
          A proportional sample of memories, summaries, and file updates across the selected
          window. Each gap records exactly how many events the sampler omitted, and every window
          is read from the live archive.
        </p>
      </div>

      <div className="timeline-header__actions">
        <div className="timeline-range-badge" aria-live="polite">
          <span className="mono-label">{isFetching ? "Reading window" : "Window span"}</span>
          <strong>{rangeLabel}</strong>
        </div>
        <ButtonLink to="/memory/new" variant="ink" size="md">
          <Icon name="plus" size={13} />
          Record Memory Crystal
        </ButtonLink>
      </div>
    </header>
  );
}
