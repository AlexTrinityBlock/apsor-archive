// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import { resolveIngestProgress } from "./ingest-progress";

const base = {
  progressPct: null,
  chunksTotal: null,
  chunksEmbedded: null,
  stageDone: null,
  stageTotal: null,
  stageUnit: null,
} as const;

test("parsing with a page count is determinate and keeps the overall percent", () => {
  const resolution = resolveIngestProgress({
    ...base,
    stage: "parsing",
    progressPct: 19,
    stageDone: 42,
    stageTotal: 120,
    stageUnit: "page",
  });

  expect(resolution.indeterminate).toBe(false);
  expect(resolution.percent).toBe(19);
  expect(resolution.stageCount).toEqual({ done: 42, total: 120, unit: "page" });
});

test("chunking with a chunk count is determinate", () => {
  const resolution = resolveIngestProgress({
    ...base,
    stage: "chunking",
    progressPct: 51,
    stageDone: 8,
    stageTotal: 20,
    stageUnit: "chunk",
  });

  expect(resolution.indeterminate).toBe(false);
  expect(resolution.percent).toBe(51);
  expect(resolution.stageCount?.unit).toBe("chunk");
});

test("a slide count is a first-class parsing unit", () => {
  const resolution = resolveIngestProgress({
    ...base,
    stage: "parsing",
    progressPct: 12,
    stageDone: 3,
    stageTotal: 14,
    stageUnit: "slide",
  });

  expect(resolution.indeterminate).toBe(false);
  expect(resolution.percent).toBe(12);
  expect(resolution.stageCount).toEqual({ done: 3, total: 14, unit: "slide" });
});

test("early stages stay indeterminate without a positive stage total", () => {
  const parsing = resolveIngestProgress({ ...base, stage: "parsing" });
  const zeroTotal = resolveIngestProgress({
    ...base,
    stage: "chunking",
    progressPct: 45,
    stageDone: 0,
    stageTotal: 0,
    stageUnit: "chunk",
  });

  expect(parsing.indeterminate).toBe(true);
  expect(parsing.stageCount).toBeNull();
  expect(zeroTotal.indeterminate).toBe(true);
});

test("an unknown stage unit remains determinate without a count line", () => {
  const resolution = resolveIngestProgress({
    ...base,
    stage: "parsing",
    progressPct: 20,
    stageDone: 2,
    stageTotal: 10,
    stageUnit: "section",
  });

  expect(resolution.indeterminate).toBe(false);
  expect(resolution.percent).toBe(20);
  expect(resolution.stageCount).toBeNull();
});

test("terminal and embedding states keep their existing precedence", () => {
  const ready = resolveIngestProgress({
    ...base,
    stage: "ready",
    progressPct: 80,
    stageDone: 5,
    stageTotal: 10,
    stageUnit: "page",
  });
  const failed = resolveIngestProgress({
    ...base,
    stage: "failed",
    progressPct: 33,
  });
  const embedding = resolveIngestProgress({
    ...base,
    stage: "embedding",
    progressPct: 76,
    chunksTotal: 20,
    chunksEmbedded: 10,
  });

  expect(ready).toEqual({ indeterminate: false, percent: 100, stageCount: null });
  expect(failed.indeterminate).toBe(false);
  expect(failed.stageCount).toBeNull();
  expect(embedding.indeterminate).toBe(false);
  expect(embedding.percent).toBe(76);
  expect(embedding.stageCount).toBeNull();
});
