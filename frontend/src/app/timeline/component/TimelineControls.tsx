import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

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
  const { t, formatNumber } = useI18n();
  const handleDateChange = (value: string) => {
    const date = parseDateInput(value);
    if (date) {
      onAnchorChange(date);
    }
  };

  return (
    <section
      className="timeline-controls"
      aria-label={t("insights.timeline.controls.aria")}
    >
      <div className="timeline-controls__nav">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onShift(-range)}
          disabled={!canGoEarlier}
          aria-label={t("insights.timeline.controls.prevAria", {
            days: formatNumber(range),
          })}
        >
          <Icon name="chevron-right" size={13} className="timeline-chevron-back" />
          {t("insights.timeline.controls.prev")}
        </Button>
        <label className="timeline-controls__date">
          <span className="mono-label">
            {t("insights.timeline.controls.windowEnd")}
          </span>
          <input
            className="input timeline-controls__date-input"
            type="date"
            value={toDateInput(anchor)}
            min={`${MIN_YEAR}-01-01`}
            max={`${MAX_YEAR}-12-31`}
            onChange={(event) => handleDateChange(event.target.value)}
            aria-label={t("insights.timeline.controls.windowEndAria")}
          />
        </label>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onShift(range)}
          disabled={!canGoLater}
          aria-label={t("insights.timeline.controls.nextAria", {
            days: formatNumber(range),
          })}
        >
          {t("insights.timeline.controls.next")}
          <Icon name="chevron-right" size={13} />
        </Button>
      </div>

      <div
        className="timeline-controls__ranges"
        role="group"
        aria-label={t("insights.timeline.controls.rangeAria")}
      >
        <span className="mono-label">
          {t("insights.timeline.controls.range")}
        </span>
        {RANGE_OPTIONS.map((days) => (
          <Button
            key={days}
            variant={range === days ? "ink" : "secondary"}
            size="sm"
            onClick={() => onRangeChange(days)}
            aria-pressed={range === days}
            aria-label={t("insights.timeline.controls.dayWindow", {
              days: formatNumber(days),
            })}
          >
            {t("insights.timeline.controls.dayShort", {
              days: formatNumber(days),
            })}
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
          <span className="timeline-switch__label">
            {t("insights.timeline.controls.includeHistory")}
          </span>
          <span className="timeline-switch__hint">
            {includeHistory
              ? t("insights.timeline.controls.historyIncluded")
              : t("insights.timeline.controls.historyActiveOnly")}
          </span>
        </span>
      </label>

      <Button
        variant="ghost"
        size="sm"
        onClick={onDemoSeason}
        title={t("insights.timeline.controls.demoSeasonTitle")}
      >
        <Icon name="ring" size={13} />
        {t("insights.timeline.controls.demoSeason")}
      </Button>
    </section>
  );
}
