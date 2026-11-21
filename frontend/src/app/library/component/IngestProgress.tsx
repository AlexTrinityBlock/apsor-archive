import { useI18n, type I18nContextValue } from "../../i18n";
import {
  INGEST_STAGE_KEYS,
  type IngestStage,
} from "./library-utils";
import {
  resolveIngestProgress,
  type IngestStageCount,
  type IngestStageUnit,
} from "./ingest-progress";

export interface IngestProgressProps {
  readonly stage?: IngestStage | null;
  readonly progressPct?: number | null;
  readonly chunksTotal?: number | null;
  readonly chunksEmbedded?: number | null;
  readonly stageDone?: number | null;
  readonly stageTotal?: number | null;
  readonly stageUnit?: string | null;
  readonly variant?: "compact" | "large";
  readonly label?: string;
  readonly className?: string;
}

interface UnitKey {
  readonly one: `library.ingest.unit.${IngestStageUnit}One`;
  readonly other: `library.ingest.unit.${IngestStageUnit}Other`;
}

const UNIT_KEYS: Record<IngestStageUnit, UnitKey> = {
  page: {
    one: "library.ingest.unit.pageOne",
    other: "library.ingest.unit.pageOther",
  },
  chunk: {
    one: "library.ingest.unit.chunkOne",
    other: "library.ingest.unit.chunkOther",
  },
  sheet: {
    one: "library.ingest.unit.sheetOne",
    other: "library.ingest.unit.sheetOther",
  },
  paragraph: {
    one: "library.ingest.unit.paragraphOne",
    other: "library.ingest.unit.paragraphOther",
  },
  image: {
    one: "library.ingest.unit.imageOne",
    other: "library.ingest.unit.imageOther",
  },
};

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

/**
 * One ingestion meter shared by the intake dialog and the drag-and-drop tray.
 * The bar is determinate once the backend reports a percentage, embedding
 * counts, or a granular parse/chunk position. Queued and stage-less states stay
 * indeterminate.
 */
export function IngestProgress({
  stage = null,
  progressPct = null,
  chunksTotal = null,
  chunksEmbedded = null,
  stageDone = null,
  stageTotal = null,
  stageUnit = null,
  variant = "compact",
  label,
  className,
}: IngestProgressProps) {
  const { t, formatNumber } = useI18n();
  const isReady = stage === "ready";
  const isFailed = stage === "failed";
  const resolution = resolveIngestProgress({
    stage,
    progressPct,
    chunksTotal,
    chunksEmbedded,
    stageDone,
    stageTotal,
    stageUnit,
  });
  const indeterminate = resolution.indeterminate;
  const percent = clampPercent(resolution.percent);
  const roundedPercent = Math.round(percent);
  const percentText = t("library.ingest.percent", {
    percent: formatNumber(roundedPercent),
  });
  const stageName =
    stage === null ? t("library.ingest.preparing") : t(INGEST_STAGE_KEYS[stage]);
  const stageLabel = label ?? stageName;
  const hasCounts =
    typeof chunksTotal === "number" &&
    chunksTotal > 0 &&
    typeof chunksEmbedded === "number";

  let countLabel: string | null = null;
  if (resolution.stageCount !== null) {
    countLabel = stageCountLabel(
      resolution.stageCount,
      stageName,
      percentText,
      t,
      formatNumber,
    );
  } else if (hasCounts) {
    countLabel = t("library.ingest.embeddingCount", {
      done: formatNumber(chunksEmbedded),
      total: formatNumber(chunksTotal),
    });
  }

  let valueText: string;
  if (indeterminate) {
    valueText = t("library.ingest.valueIndeterminate", {
      stage: stageLabel,
      note: t("library.ingest.notMeasured"),
    });
  } else if (countLabel !== null) {
    valueText = countLabel;
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

function stageCountLabel(
  count: IngestStageCount,
  stageName: string,
  percentText: string,
  t: I18nContextValue["t"],
  formatNumber: I18nContextValue["formatNumber"],
): string {
  const keys = UNIT_KEYS[count.unit];
  const unit = t(count.total === 1 ? keys.one : keys.other);
  const measured = t("library.ingest.stageCount", {
    done: formatNumber(count.done),
    total: formatNumber(count.total),
    unit,
  });
  return t("library.ingest.stageValue", {
    stage: stageName,
    count: measured,
    percent: percentText,
  });
}
