import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

import { parseDateInput, toDateInput } from "./helpers";

const QUICK_RANGES = [7, 14, 30, 90] as const;

interface TimelineControlsProps {
  readonly anchor: Date;
  readonly range: number;
  readonly includeHistory: boolean;
  readonly caption: string;
  readonly onAnchorChange: (date: Date) => void;
  readonly onShift: (days: number) => void;
  readonly onRangeChange: (range: number) => void;
  readonly onHistoryChange: (includeHistory: boolean) => void;
  readonly onDemoSeason: () => void;
}

/** Date anchor, period shifting, quick windows, and the history toggle. */
export function TimelineControls({
  anchor,
  range,
  includeHistory,
  caption,
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
    <section className="timeline-controls reveal reveal-2" aria-label="Timeline range controls">
      <div className="timeline-controls__main">
        <div className="timeline-controls__period">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onShift(-range)}
            aria-label={`Prev: previous period, ${range} days earlier`}
          >
            <Icon name="chevron-right" size={14} className="timeline-controls__chevron is-back" />
            Prev
          </Button>
          <label className="timeline-date-field">
            <span className="eyebrow">Anchor day</span>
            <input
              type="date"
              value={toDateInput(anchor)}
              min="1900-01-01"
              max="2200-12-31"
              onChange={(event) => handleDateChange(event.target.value)}
            />
          </label>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onShift(range)}
            aria-label={`Next period, ${range} days later`}
          >
            Next
            <Icon name="chevron-right" size={14} />
          </Button>
        </div>

        <div className="timeline-controls__windows" role="group" aria-label="Quick range lengths">
          <span className="eyebrow">Window</span>
          {QUICK_RANGES.map((days) => (
            <Button
              key={days}
              variant={range === days ? "ink" : "secondary"}
              size="sm"
              onClick={() => onRangeChange(days)}
              aria-pressed={range === days}
            >
              {days} d
            </Button>
          ))}
        </div>

        <div className="timeline-controls__presets">
          <Button variant="secondary" size="sm" onClick={onDemoSeason}>
            <Icon name="ring" size={14} />
            September 2026
          </Button>
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
          <span>Include deprecated history</span>
        </label>
      </div>

      <div className="timeline-controls__readout" aria-live="polite">
        <span className="eyebrow">Displayed range</span>
        <strong>{caption}</strong>
        <span>
          {range} {range === 1 ? "day" : "days"} {"\u00b7"} anchor at the right edge
        </span>
      </div>
    </section>
  );
}
