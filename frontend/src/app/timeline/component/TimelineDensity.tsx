import type { TimelineResponseSchema } from "../../generated-apis-types/schemas";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { formatNumber } from "../../../lib/format";

import { formatDay } from "./helpers";

interface TimelineDensityProps {
  readonly data: TimelineResponseSchema;
  readonly caption: string;
}

/** Per-day stacked bars for memories, summaries, and file updates. */
export function TimelineDensity({ data, caption }: TimelineDensityProps) {
  const totals = data.density.reduce(
    (sum, day) => ({
      files: sum.files + day.file_count,
      memories: sum.memories + day.memory_count,
      summaries: sum.summaries + day.summary_count,
    }),
    { files: 0, memories: 0, summaries: 0 },
  );
  const maxDay = data.density.reduce(
    (max, day) => Math.max(max, day.file_count + day.memory_count + day.summary_count),
    1,
  );

  return (
    <Panel
      eyebrow="Sparse sample"
      title="Density along the range"
      className="timeline-density reveal reveal-3"
      action={
        <Badge tone={data.truncated ? "vermilion" : "neutral"}>
          {data.truncated ? "Truncated at 2000 / kind" : `${data.day_range} days`}
        </Badge>
      }
    >
      <dl className="timeline-density__stats">
        <div>
          <dt>Total events</dt>
          <dd>{formatNumber(data.total)}</dd>
        </div>
        <div>
          <dt>Sampled</dt>
          <dd>{formatNumber(data.sampled)}</dd>
        </div>
        <div>
          <dt>Skipped</dt>
          <dd>{formatNumber(data.skipped)}</dd>
        </div>
        <div className="timeline-density__caption">
          <dt>Window</dt>
          <dd>{caption}</dd>
        </div>
      </dl>

      <div className="timeline-density__plot-wrap">
        {data.density.length === 0 ? (
          <div className="timeline-density__empty">
            <Icon name="info" size={18} />
            <p>
              {data.total === 0
                ? "No density to plot: this range contains no memories, summaries, or file updates."
                : "No per-day density was returned for this range, even though the endpoint counted events."}
            </p>
          </div>
        ) : (
          <ol className="timeline-density__plot" aria-label={`Daily event density for ${caption}`}>
            {data.density.map((day) => {
              const total = day.file_count + day.memory_count + day.summary_count;
              const height = Math.max(3, (total / maxDay) * 100);
              const label = `${formatDay(day.date)}: ${day.memory_count} memories, ${day.summary_count} summaries, ${day.file_count} file updates`;
              return (
                <li key={day.date} className="timeline-density__day" title={label}>
                  <span className="visually-hidden">{label}</span>
                  <span
                    className="timeline-density__bar"
                    style={{ height: `${height}%` }}
                    aria-hidden="true"
                  >
                    {day.file_count > 0 ? (
                      <span
                        className="timeline-density__segment is-file"
                        style={{ flexGrow: day.file_count }}
                      />
                    ) : null}
                    {day.memory_count > 0 ? (
                      <span
                        className="timeline-density__segment is-memory"
                        style={{ flexGrow: day.memory_count }}
                      />
                    ) : null}
                    {day.summary_count > 0 ? (
                      <span
                        className="timeline-density__segment is-summary"
                        style={{ flexGrow: day.summary_count }}
                      />
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <div className="timeline-density__legend" aria-label="Density legend">
        <span>
          <i className="timeline-swatch is-file" aria-hidden="true" />
          {formatNumber(totals.files)} {totals.files === 1 ? "file update" : "file updates"}
        </span>
        <span>
          <i className="timeline-swatch is-memory" aria-hidden="true" />
          {formatNumber(totals.memories)} {totals.memories === 1 ? "memory" : "memories"}
        </span>
        <span>
          <i className="timeline-swatch is-summary" aria-hidden="true" />
          {formatNumber(totals.summaries)} {totals.summaries === 1 ? "summary" : "summaries"}
        </span>
        <span className="timeline-density__legend-note">
          Each bar is one day with events; plain days are not drawn.
        </span>
      </div>
    </Panel>
  );
}
