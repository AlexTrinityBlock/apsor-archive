import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

import {
  MAX_YEAR,
  MIN_YEAR,
  RANGE_OPTIONS,
  parseDateInput,
  toDateInput,
} from "./helpers";

interface TimelineControlsProps {
  readonly anchor: Date;
  readonly range: number;
  readonly includeHistory: boolean;
  readonly canGoEarlier: boolean;
  readonly canGoLater: boolean;
  readonly onAnchorChange: (date: Date) => void;
  readonly onShift: (days: number) => void;
  readonly onRangeChange: (range: number) => void;
  readonly onHistoryChange: (includeHistory: boolean) => void;
  readonly onDemoSeason: () => void;
}

/** Compact functional controls for the timeline's date window and sampling. */
export function TimelineControls({
  anchor,
  range,
  includeHistory,
  canGoEarlier,
  canGoLater,
  onAnchorChange,
  onShift,
  onRangeChange,
  onHistoryChange,
  onDemoSeason,
}: TimelineControlsProps) {
  const handleDateChange = (value: string) => {
    const date = parseDateInput(value);
    if (date) {
      onAnchorChange(date);
    }
  };

  return (
    <section className="timeline-controls" aria-label="Timeline window controls">
      <div className="timeline-controls__nav">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onShift(-range)}
          disabled={!canGoEarlier}
          aria-label={`Previous window, ${range} days earlier`}
        >
          <Icon name="chevron-right" size={13} className="timeline-chevron-back" />
          Prev
        </Button>
        <label className="timeline-controls__date">
          <span className="mono-label">Window end</span>
          <input
            className="input timeline-controls__date-input"
            type="date"
            value={toDateInput(anchor)}
            min={`${MIN_YEAR}-01-01`}
            max={`${MAX_YEAR}-12-31`}
            onChange={(event) => handleDateChange(event.target.value)}
            aria-label="Window end date"
          />
        </label>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onShift(range)}
          disabled={!canGoLater}
          aria-label={`Next window, ${range} days later`}
        >
          Next
          <Icon name="chevron-right" size={13} />
        </Button>
      </div>

      <div className="timeline-controls__ranges" role="group" aria-label="Window length">
        <span className="mono-label">Range</span>
        {RANGE_OPTIONS.map((days) => (
          <Button
            key={days}
            variant={range === days ? "ink" : "secondary"}
            size="sm"
            onClick={() => onRangeChange(days)}
            aria-pressed={range === days}
            aria-label={`${days} day window`}
          >
            {days}d
          </Button>
        ))}
      </div>

      <label className="timeline-switch">
        <input
          type="checkbox"
          checked={includeHistory}
          onChange={(event) => onHistoryChange(event.target.checked)}
        />
        <span className="timeline-switch__track" aria-hidden="true">
          <span className="timeline-switch__knob" />
        </span>
        <span className="timeline-switch__copy">
          <span className="timeline-switch__label">Include history</span>
          <span className="timeline-switch__hint">
            {includeHistory ? "Deprecated memories included" : "Active memories only"}
          </span>
        </span>
      </label>

      <Button
        variant="ghost"
        size="sm"
        onClick={onDemoSeason}
        title="Read the seeded demo season"
      >
        <Icon name="ring" size={13} />
        Try demo season
      </Button>
    </section>
  );
}
