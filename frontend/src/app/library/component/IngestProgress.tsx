import { useI18n } from "../../i18n";
import {
  INGEST_STAGE_KEYS,
  type IngestStage,
} from "./library-utils";

const EARLY_STAGES: readonly IngestStage[] = ["queued", "parsing", "chunking"];

export interface IngestProgressProps {
  readonly stage?: IngestStage | null;
  readonly progressPct?: number | null;
  readonly chunksTotal?: number | null;
  readonly chunksEmbedded?: number | null;
  readonly variant?: "compact" | "large";
  readonly label?: string;
  readonly className?: string;
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

function resolvePercent(
  isReady: boolean,
  hasCounts: boolean,
  chunksEmbedded: number,
  chunksTotal: number,
  progressPct: number | null,
): number {
  if (isReady) {
    return 100;
  }
  if (typeof progressPct === "number") {
    return progressPct;
  }
  if (hasCounts) {
    return (chunksEmbedded / chunksTotal) * 100;
  }
  return 0;
}

/**
 * One ingestion meter shared by the intake dialog and the drag-and-drop tray.
 * The bar is determinate once the backend reports a percentage or embedding
 * counts; queued, parsing, and chunking stay indeterminate until then.
 */
export function IngestProgress({
  stage = null,
  progressPct = null,
  chunksTotal = null,
  chunksEmbedded = null,
  variant = "compact",
  label,
  className,
}: IngestProgressProps) {
  const { t, formatNumber } = useI18n();
  const isReady = stage === "ready";
  const isFailed = stage === "failed";
  const hasCounts =
    typeof chunksTotal === "number" &&
    chunksTotal > 0 &&
    typeof chunksEmbedded === "number";
  const earlyStage =
    stage === null || EARLY_STAGES.includes(stage);
  const indeterminate = !isReady && !isFailed && !hasCounts && earlyStage;

  const measuredPct = resolvePercent(
    isReady,
    hasCounts,
    chunksEmbedded ?? 0,
    chunksTotal ?? 0,
    progressPct,
  );
  const percent = clampPercent(measuredPct);
  const roundedPercent = Math.round(percent);
  const percentText = t("library.ingest.percent", {
    percent: formatNumber(roundedPercent),
  });
  const stageLabel =
    label ?? (stage === null ? t("library.ingest.preparing") : t(INGEST_STAGE_KEYS[stage]));
  const countLabel = hasCounts
    ? t("library.ingest.embeddingCount", {
        done: formatNumber(chunksEmbedded),
        total: formatNumber(chunksTotal),
      })
    : null;
  let valueText: string;
  if (indeterminate) {
    valueText = t("library.ingest.valueIndeterminate", {
      stage: stageLabel,
      note: t("library.ingest.notMeasured"),
    });
  } else if (countLabel !== null) {
    valueText = t("library.ingest.valueWithCount", {
      stage: stageLabel,
      count: countLabel,
      percent: percentText,
    });
  } else {
    valueText = t("library.ingest.value", {
      stage: stageLabel,
      percent: percentText,
    });
  }

  const classes = [
    "ingest-progress",
    `ingest-progress--${variant}`,
    indeterminate ? "is-indeterminate" : null,
    isReady ? "is-ready" : null,
    isFailed ? "is-failed" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <div className="ingest-progress__head">
        <span className="ingest-progress__stage">{stageLabel}</span>
        {indeterminate ? null : (
          <span className="ingest-progress__percent">{percentText}</span>
        )}
      </div>
      <div
        className="ingest-progress__track"
        role="progressbar"
        aria-label={t("library.ingest.ariaProgress", { stage: stageLabel })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : roundedPercent}
        aria-valuetext={valueText}
      >
        <span
          className="ingest-progress__fill"
          style={indeterminate ? undefined : { width: `${percent}%` }}
        />
      </div>
      {countLabel ? <span className="ingest-progress__count">{countLabel}</span> : null}
    </div>
  );
}
