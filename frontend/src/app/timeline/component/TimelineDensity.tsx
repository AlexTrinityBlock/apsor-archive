import type { TimelineResponseSchema } from "../../generated-apis-types/schemas";

import { formatNumber } from "../../../lib/format";

import {
  addDays,
  differenceInCalendarDays,
  formatCalendarDay,
  formatShortDay,
  isWithinApiRange,
  parseIsoDay,
  toDateInput,
} from "./helpers";

interface TimelineDensityProps {
  readonly data: TimelineResponseSchema;
  readonly anchor: Date;
  readonly onAnchorChange: (date: Date) => void;
}

interface DensityBar {
  readonly date: string;
  readonly day: Date;
  readonly memoryCount: number;
  readonly summaryCount: number;
  readonly fileCount: number;
  readonly xPercent: number;
  readonly height: number;
  readonly tier: "quiet" | "mid" | "peak";
  readonly canAnchor: boolean;
}

function densityTier(ratio: number): "quiet" | "mid" | "peak" {
  if (ratio === 1) {
    return "peak";
  }
  if (ratio >= 0.5) {
    return "mid";
  }
  return "quiet";
}

function densityBarLabel(bar: DensityBar): string {
  return [
    `${bar.memoryCount} ${bar.memoryCount === 1 ? "memory" : "memories"}`,
    `${bar.summaryCount} ${bar.summaryCount === 1 ? "summary" : "summaries"}`,
    `${bar.fileCount} ${bar.fileCount === 1 ? "file update" : "file updates"}`,
  ].join(", ");
}

/** The 68px hairline density strip; each stem is one active day in the API window. */
export function TimelineDensity({ data, anchor, onAnchorChange }: TimelineDensityProps) {
  const startDay = parseIsoDay(data.range_start);
  const dayRange = Math.max(1, data.day_range);
  const maxTotal = Math.max(
    1,
    ...data.density.map((day) => day.memory_count + day.summary_count + day.file_count),
  );
  const anchorKey = toDateInput(anchor);

  const bars: DensityBar[] = [];
  for (const day of data.density) {
    const date = parseIsoDay(day.date);
    if (!date) {
      continue;
    }
    const offset = startDay ? differenceInCalendarDays(date, startDay) : 0;
    const clampedOffset = Math.min(dayRange - 1, Math.max(0, offset));
    const total = day.memory_count + day.summary_count + day.file_count;
    const ratio = total / maxTotal;
    bars.push({
      date: day.date,
      day: date,
      memoryCount: day.memory_count,
      summaryCount: day.summary_count,
      fileCount: day.file_count,
      xPercent: ((clampedOffset + 0.5) / dayRange) * 100,
      height: Math.max(3, ratio * 42),
      tier: densityTier(ratio),
      canAnchor: isWithinApiRange(date),
    });
  }

  const totals = data.density.reduce(
    (sum, day) => ({
      memories: sum.memories + day.memory_count,
      summaries: sum.summaries + day.summary_count,
      files: sum.files + day.file_count,
    }),
    { memories: 0, summaries: 0, files: 0 },
  );

  const tickCount = Math.min(5, dayRange);
  const axisTicks =
    startDay !== null
      ? Array.from({ length: tickCount }, (_, index) => {
          const offset =
            tickCount === 1 ? 0 : Math.round((index * (dayRange - 1)) / (tickCount - 1));
          return addDays(startDay, offset);
        })
      : [];

  const hitWidthPercent = Math.min(1.6, Math.max(0.2, 80 / dayRange));
  const hasUnanchorableBars = bars.some((bar) => !bar.canAnchor);

  return (
    <section className="timeline-density" aria-label="Timeline density strip">
      <div className="timeline-density__head">
        <div className="timeline-density__title-group">
          <h2 className="timeline-density__title">Growth-ring density across the window</h2>
          <span className="timeline-density__protocol">0.7px hairline protocol</span>
        </div>
        <span className="timeline-density__telemetry">
          {formatNumber(dayRange)}-day window {"\u00b7"} {formatNumber(data.density.length)} active{" "}
          {data.density.length === 1 ? "day" : "days"} {"\u00b7"}{" "}
          {formatNumber(data.sampled)} sampled of {formatNumber(data.total)}
        </span>
      </div>

      <div className="timeline-density__canvas">
        <svg
          className="timeline-density__svg"
          viewBox="0 0 1000 68"
          preserveAspectRatio="none"
          aria-hidden="true"
          focusable="false"
        >
          <line
            className="timeline-density__guideline"
            x1="0"
            y1="14"
            x2="1000"
            y2="14"
            vectorEffect="non-scaling-stroke"
          />
          <line
            className="timeline-density__guideline"
            x1="0"
            y1="32"
            x2="1000"
            y2="32"
            vectorEffect="non-scaling-stroke"
          />
          <line
            className="timeline-density__baseline"
            x1="0"
            y1="52"
            x2="1000"
            y2="52"
            vectorEffect="non-scaling-stroke"
          />
          {bars.map((bar) => (
            <line
              key={bar.date}
              className={`timeline-density__stem timeline-density__stem--${bar.tier}`}
              x1={bar.xPercent * 10}
              y1={52 - bar.height}
              x2={bar.xPercent * 10}
              y2="52"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {bars
            .filter((bar) => bar.date === anchorKey)
            .map((bar) => (
              <line
                key={`cursor-${bar.date}`}
                className="timeline-density__cursor"
                x1={bar.xPercent * 10}
                y1="2"
                x2={bar.xPercent * 10}
                y2="56"
                vectorEffect="non-scaling-stroke"
              />
            ))}
        </svg>

        {bars.map((bar) => (
          <button
            key={bar.date}
            type="button"
            className={
              bar.date === anchorKey
                ? "timeline-density__bar is-anchor"
                : "timeline-density__bar"
            }
            style={{ left: `${bar.xPercent}%`, width: `${hitWidthPercent}%` }}
            title={
              bar.canAnchor
                ? `${formatCalendarDay(bar.day)} \u00b7 ${densityBarLabel(bar)}`
                : `${formatCalendarDay(bar.day)} is outside the supported 1900–2200 window ends`
            }
            aria-label={
              bar.canAnchor
                ? `Set window end to ${formatCalendarDay(bar.day)}. ${densityBarLabel(bar)}.`
                : `${formatCalendarDay(bar.day)} is outside the supported 1900–2200 window ends. ${densityBarLabel(bar)}.`
            }
            aria-current={bar.date === anchorKey ? "date" : undefined}
            disabled={!bar.canAnchor}
            onClick={() => onAnchorChange(bar.day)}
          />
        ))}

        {bars.length === 0 ? (
          <p className="timeline-density__empty-note">
            No dated events in this window. The strip stays flat until the archive has something to
            plot.
          </p>
        ) : null}
      </div>

      {axisTicks.length > 0 ? (
        <div className="timeline-density__axis" aria-hidden="true">
          {axisTicks.map((tick, index) => (
            <span key={`axis-${index}-${toDateInput(tick)}`} className="timeline-density__axis-tick">
              {formatShortDay(tick)}
              {index === axisTicks.length - 1 ? " \u00b7 end" : ""}
            </span>
          ))}
        </div>
      ) : null}

      <div className="timeline-density__legend">
        <span className="timeline-density__legend-label">Window composition</span>
        <span className="timeline-density__legend-item">
          <i
            className="timeline-density__swatch timeline-density__swatch--memory"
            aria-hidden="true"
          />
          {formatNumber(totals.memories)} {totals.memories === 1 ? "memory" : "memories"}
        </span>
        <span className="timeline-density__legend-item">
          <i
            className="timeline-density__swatch timeline-density__swatch--summary"
            aria-hidden="true"
          />
          {formatNumber(totals.summaries)} {totals.summaries === 1 ? "summary" : "summaries"}
        </span>
        <span className="timeline-density__legend-item">
          <i className="timeline-density__swatch timeline-density__swatch--file" aria-hidden="true" />
          {formatNumber(totals.files)} {totals.files === 1 ? "file update" : "file updates"}
        </span>
        {hasUnanchorableBars ? (
          <span className="timeline-density__anchor-note">
            Window end must be within 1900–2200
          </span>
        ) : null}
        {data.truncated ? (
          <span className="timeline-density__truncated">Truncated at the per-kind event cap</span>
        ) : null}
        <span className="timeline-density__legend-hint">
          Click a stem to move the window end to that day.
        </span>
      </div>
    </section>
  );
}
