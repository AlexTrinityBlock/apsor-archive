import type { IngestStage } from "./library-utils";

/** Units the backend tracker can report for a granular stage. */
export const INGEST_STAGE_UNITS = [
  "page",
  "chunk",
  "sheet",
  "paragraph",
  "image",
  "slide",
] as const;

export type IngestStageUnit = (typeof INGEST_STAGE_UNITS)[number];

/** A determinate parse/chunk position reported by the durable job. */
export interface IngestStageCount {
  readonly done: number;
  readonly total: number;
  readonly unit: IngestStageUnit;
}

export interface IngestProgressResolution {
  readonly indeterminate: boolean;
  readonly percent: number;
  readonly stageCount: IngestStageCount | null;
}

export interface IngestProgressInput {
  readonly stage: IngestStage | null;
  readonly progressPct: number | null;
  readonly chunksTotal: number | null;
  readonly chunksEmbedded: number | null;
  readonly stageDone: number | null;
  readonly stageTotal: number | null;
  readonly stageUnit: string | null;
}

const EARLY_STAGES: readonly IngestStage[] = ["queued", "parsing", "chunking"];

function isStageUnit(value: string | null): value is IngestStageUnit {
  return value !== null && (INGEST_STAGE_UNITS as readonly string[]).includes(value);
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

/**
 * Resolves the one progress meter from typed backend fields.
 *
 * Parsing and chunking become determinate only when the backend has published a
 * positive total and a current count. Terminal, embedding, and unknown states
 * keep their previous precedence, so a stage count can never mask a finished or
 * failed job.
 */
export function resolveIngestProgress({
  stage,
  progressPct,
  chunksTotal,
  chunksEmbedded,
  stageDone,
  stageTotal,
  stageUnit,
}: IngestProgressInput): IngestProgressResolution {
  if (stage === "ready") {
    return { indeterminate: false, percent: 100, stageCount: null };
  }
  if (stage === "failed") {
    return {
      indeterminate: false,
      percent: clampPercent(progressPct ?? 0),
      stageCount: null,
    };
  }

  const hasCounts =
    typeof chunksTotal === "number" &&
    chunksTotal > 0 &&
    typeof chunksEmbedded === "number";
  if (hasCounts) {
    const measured =
      typeof progressPct === "number"
        ? progressPct
        : (chunksEmbedded / chunksTotal) * 100;
    return {
      indeterminate: false,
      percent: clampPercent(measured),
      stageCount: null,
    };
  }

  const hasStageCount =
    (stage === "parsing" || stage === "chunking") &&
    typeof stageTotal === "number" &&
    stageTotal > 0 &&
    typeof stageDone === "number";
  if (hasStageCount) {
    const measured =
      typeof progressPct === "number"
        ? progressPct
        : (stageDone / stageTotal) * 100;
    return {
      indeterminate: false,
      percent: clampPercent(measured),
      stageCount: isStageUnit(stageUnit)
        ? { done: stageDone, total: stageTotal, unit: stageUnit }
        : null,
    };
  }

  const earlyStage = stage === null || EARLY_STAGES.includes(stage);
  return {
    indeterminate: earlyStage,
    percent: clampPercent(progressPct ?? 0),
    stageCount: null,
  };
}
