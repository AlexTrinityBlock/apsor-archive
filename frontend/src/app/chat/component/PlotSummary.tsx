import { useI18n } from "../../i18n";
import { readPlotSpec } from "../plot";
import { stringValue, type JsonRecord } from "../types";

interface PlotSummaryProps {
  /** Persisted display arguments (`title`, `caption`) or a live tool payload. */
  readonly arguments: JsonRecord | null;
  /** Tool-result data carrying `plot.figure` and `plot.stats`. */
  readonly data: unknown;
  /** Optional anchor to the transcript entry that renders the chart. */
  readonly chartHref?: string | null;
}

/**
 * Human-readable render_plot receipt.
 *
 * The figure itself stays out of the arguments panel; only the title, caption,
 * trace/point counts, and byte size are shown. Missing values are omitted
 * instead of rendered as JSON.
 */
export function PlotSummary({
  arguments: args,
  data,
  chartHref = null,
}: PlotSummaryProps) {
  const { t, formatNumber } = useI18n();
  const spec = readPlotSpec(data);
  const title = stringValue(args?.title) ?? spec?.title ?? t("chat.plot.title");
  const caption = stringValue(args?.caption) ?? spec?.caption;
  const stats = spec?.stats;

  return (
    <dl className="plot-summary">
      <div>
        <dt>{t("chat.plot.summaryTitle")}</dt>
        <dd>{title}</dd>
      </div>
      {caption ? (
        <div>
          <dt>{t("chat.plot.summaryCaption")}</dt>
          <dd>{caption}</dd>
        </div>
      ) : null}
      {stats ? (
        <>
          <div>
            <dt>{t("chat.plot.summaryTraces")}</dt>
            <dd>{formatNumber(stats.traceCount)}</dd>
          </div>
          <div>
            <dt>{t("chat.plot.summaryPoints")}</dt>
            <dd>{formatNumber(stats.pointCount)}</dd>
          </div>
          {stats.byteSize === null ? null : (
            <div>
              <dt>{t("chat.plot.summaryBytes")}</dt>
              <dd>
                {t("chat.plot.bytesValue", {
                  value: formatNumber(stats.byteSize),
                })}
              </dd>
            </div>
          )}
        </>
      ) : null}
      {chartHref ? (
        <a className="plot-summary__link" href={chartHref}>
          {t("chat.plot.viewChart")}
        </a>
      ) : null}
    </dl>
  );
}
