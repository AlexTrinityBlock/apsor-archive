import { formatNumber } from "../../../lib/format";
import {
  INGEST_STAGE_LABELS,
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

function buildValueText(
  stageLabel: string,
  countLabel: string | null,
  roundedPercent: number,
  indeterminate: boolean,
): string {
  if (indeterminate) {
    return `${stageLabel} · progress not measured yet`;
  }
  if (countLabel !== null) {
    return `${stageLabel} · ${countLabel} · ${roundedPercent}%`;
  }
  return `${stageLabel} · ${roundedPercent}%`;
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
  const stageLabel = label ?? (stage === null ? "Preparing" : INGEST_STAGE_LABELS[stage]);
  const countLabel = hasCounts
    ? `Embedding ${formatNumber(chunksEmbedded)} / ${formatNumber(chunksTotal)}`
    : null;
  const valueText = buildValueText(stageLabel, countLabel, roundedPercent, indeterminate);

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
          <span className="ingest-progress__percent">{roundedPercent}%</span>
        )}
      </div>
      <div
        className="ingest-progress__track"
        role="progressbar"
        aria-label={`${stageLabel} progress`}
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
