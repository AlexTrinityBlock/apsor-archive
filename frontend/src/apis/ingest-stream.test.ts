// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import type { IngestJobSchema } from "../app/generated-apis-types/schemas";
import {
  isNewerIngestUpdate,
  mergeIngestProgressEvent,
  type IngestProgressEvent,
} from "./ingest-stream";

const job: IngestJobSchema = {
  attempts: 1,
  chunks_embedded: null,
  chunks_total: null,
  created_at: "2026-11-21T10:00:00Z",
  error_code: null,
  error_detail: null,
  file_id: null,
  file_name: "report.pdf",
  finished_at: null,
  id: 9,
  mime_type: "application/pdf",
  occurred_at: null,
  path: "/reports/report.pdf",
  progress_pct: 19,
  size_bytes: 1200,
  source_file_id: null,
  source_kind: "upload",
  stage: "Extracting 42/120 page",
  stage_done: 42,
  stage_total: 120,
  stage_unit: "page",
  started_at: "2026-11-21T10:00:01Z",
  status: "parsing",
  updated_at: "2026-11-21T10:00:02Z",
};

const event: IngestProgressEvent = {
  id: 9,
  status: "chunking",
  stage: "Splitting text into chunks",
  progress_pct: 60,
  stage_done: null,
  stage_total: null,
  stage_unit: null,
  chunks_total: 20,
  chunks_embedded: null,
  file_id: null,
  error_code: null,
  error_detail: null,
  updated_at: "2026-11-21T10:00:05Z",
};

test("a compact event replaces typed progress and clears finished stage counts", () => {
  const merged = mergeIngestProgressEvent(job, event);

  expect(merged.status).toBe("chunking");
  expect(merged.progress_pct).toBe(60);
  expect(merged.chunks_total).toBe(20);
  expect(merged.stage_done).toBeNull();
  expect(merged.stage_total).toBeNull();
  expect(merged.stage_unit).toBeNull();
  expect(merged.path).toBe("/reports/report.pdf");
  expect(merged.file_name).toBe("report.pdf");
  expect(merged.updated_at).toBe("2026-11-21T10:00:05Z");
});

test("out-of-order and duplicate timestamps are rejected", () => {
  expect(isNewerIngestUpdate(job.updated_at, event.updated_at)).toBe(true);
  expect(isNewerIngestUpdate(event.updated_at, job.updated_at)).toBe(false);
  expect(isNewerIngestUpdate(event.updated_at, event.updated_at)).toBe(false);
});
