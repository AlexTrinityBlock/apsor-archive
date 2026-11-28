# Knowledge Module — Agent Guide

The knowledge slice owns the archive itself: versioned files, the folder tree, extracted text and chunks, embeddings, hybrid search, memories and supersession, periodic summaries, sparse and complete timeline reads, durable ingestion, and provider configuration.

## Purpose

Keep file lineage, search visibility, and memory history consistent across synchronous API calls, background ingestion, and retrieval. A write is not complete until current rows, chunks, embeddings, and cache invalidation agree.

## Architecture

- `FileModel` is one version row, not one path. When a new upload or Markdown update is published over an existing path, it inserts a new row, points `supersedes_file_id` at the old row, and marks the old row non-current. A partial unique index permits one current, non-deleted row per `raw_file_path`.
- Historical file rows remain readable by id, but mutations require a current row. `update_markdown_content`, move, copy, and delete all go through `_require_current_file_for_update`, which locks the row with `get_current_for_update` (`SELECT ... FOR UPDATE`). A historical or deleted id returns `404 file_not_found`.
- A move changes only `raw_file_path` and `file_name`, preserving id, version, chunks, embeddings, storage key, and links. A copy creates a new current row at version 1, clones stored originals when present, rebuilds chunks/embeddings, and does not copy lineage or supersession.
- `FolderModel` is an explicit tree so empty folders and folder identity are real. File leaves are derived from `file.raw_file_path`. Folder creation is idempotent and creates missing ancestors; a path occupied by the other node kind is `409 tree_path_conflict`.
- `LocalFileStorage` writes opaque relative keys under the configured data directory and refuses path escapes. Original bytes and database rows must be cleaned up together when an ingestion or copy fails.
- `ChunkModel` is one polymorphic search table for `file`, `memory`, `summary`, and `history` sources. It stores content, char/token counts, JSONB embeddings, embedding model, and `is_current`; `chunk_ngram` stores term frequencies for BM25. Source metadata stays in the owning table. A history row's `source_id` is an immutable `agent_entry` id and its content is one raw 256-character window (32-character overlap, stride 224).
- `IndexerService` is the single chunk/embedding pipeline. It splits text, writes chunks and n-grams, embeds in bounded batches with bounded retry, and can stage rows (`is_current=False`) until a durable job publishes them. An embedding failure (billing, quota, auth, outage, spent allowance) never fails ingestion: the chunk keeps its text and n-grams with `embedding IS NULL` (pending; stored as SQL NULL via `JSONB(none_as_null=True)`), and only a mid-job model/dimension change (`EmbeddingConfigurationChangedError`) fails a strict worker job. The worker-only `EmbeddingBackfill` (`service/embedding_backfill.py`, rules in `domain/embedding_backfill_domain.py`) fills pending vectors per owner with a global circuit breaker; per-chunk 400/413/422 failures count in `chunk.embedding_failures` up to 5. Root status/retry: `GET /system/embedding-backfill`, `POST /system/embedding-backfill/retry` (the nudge reaches the worker through the cache).
- Vision extraction indexes more than OCR. `VisionDocument` carries the verbatim `text`, GitHub-Flavored Markdown `tables`, and a visual `description`; `FileService` composes them into the extracted text under English section headings. Two editable prompt templates live in `ingest_config`: image mode for standalone images and DOCX/PPTX media (full description, tables, and reading-order text) and document-page mode for scanned PDFs (OCR plus tables plus a brief layout note). `vision_description_language` controls `description`, `caption`, `title`, `summary`, and `tags`; OCR text and table cell text are never translated. Each vision-extracted file records the SHA-256 of the exact rendered system prompt, its mode, and the language. A saved prompt or language applies to future ingests only; existing files keep their extraction until an explicit re-ingest creates a new version.
- Spreadsheet extraction is text-only and never uses vision. calamine reads `.xlsx`, `.xls`, `.xlsm`, and `.ods`; openpyxl is a fallback that recovers formula text only for OOXML `.xlsx`/`.xlsm` cells whose cached value is empty. Each visible or hidden worksheet renders as a GitHub-Flavored Markdown table under `## Sheet: <name>`; the first non-empty row is the header, merged cells repeat their top-left value, and hidden sheets are marked `(hidden)`. Extraction is bounded to 10,000 rows per sheet, 100 columns, 4,000 characters per cell, and a workbook budget that is lowered to stay below the 500-chunk-per-file ceiling. Before calamine runs, `spreadsheet_guard.py` rejects more than 10,000 zip entries, a single entry above 32 MiB, more than 64 MiB of declared uncompressed data, or a declared grid above 200,000 rows / 1,024 columns / 2,000,000 cells as `spreadsheet_archive_too_large`; the grid check specifically stops ODS repeated rows/columns and forged XLSX dimensions from exhausting memory. Re-ingest remains vision-only, so extraction changes apply only to a re-uploaded spreadsheet.
- Re-ingest is a durable `file_ingest_job` with `source_kind='reingest'` and `source_file_id`. It stores no payload (`storage_key`/`storage_backend` are NULL), reads the current source original through the owner-scoped file service, forces the vision pass, and stages a new version. `publish_pending(expected_current_file_id=...)` refuses to publish if a newer upload became current, and failure/recovery must never delete the shared source bytes.
- Chunk boundaries are stored per file. The singleton `ingest_config` row supplies future chunk sizes; changing `chunk_target_chars` or `chunk_overlap_chars` affects only future ingests, and existing files keep their boundaries until re-ingested.
- Durable ingestion uses `file_ingest_job` with `queued → parsing → chunking → embedding → summarizing → ready`, or `failed`. The worker claims with `SELECT ... FOR UPDATE SKIP LOCKED`, owns staged rows, publishes only on success, discards them on failure, and requeues stale leases after a crash. While parsing or chunking, nullable `stage_done`/`stage_total`/`stage_unit` describe the current page, chunk, DOCX paragraph/row, PPTX slide, or rendered PDF page; the worker's one-second reporter writes them, keeps `updated_at` fresh, and clears them at the embedding/publish/terminal boundary. Spreadsheet sheet progress remains coarse.
- Only the dedicated worker process (or the API in the opt-in `APSOR_INGEST_WORKER_ENABLED=true` dev mode) drains durable jobs. The deprecated synchronous `POST /files` (`uploadFile`) still extracts inside the API request, and `POST /files/text`, Markdown updates, copies, memories, and summaries index in the request; new file-upload clients must use `uploadFileAsync`.
- Live progress uses Valkey Pub/Sub as an ephemeral hint, never a second ledger. `GET /files/ingest-jobs/{id}/events` streams a compact snapshot over SSE and falls back to one-second owner-scoped polling if the broker is unavailable; the JSON job endpoint and the browser's polling helper remain the durable fallback.
- RabbitMQ (`apsor.ingest`) is an optional low-latency dispatch path, never a second ledger. The API publishes persistent `{job_id, retry_count}` messages, the consumer uses manual ack with prefetch 1 so a crash redelivers the unacked delivery, and retry outcomes use a TTL retry queue capped by a dispatch-retry limit. Every message is re-read from `file_ingest_job` and claimed there; duplicate or missing messages only fall back to the one-second database polling worker.
- `search_service.py` runs BM25 over CJK bigrams and Latin terms, optional vector recall by cosine similarity, and reciprocal-rank fusion. Results are selected per source kind, de-duplicated by chunk, hydrated, and cached under the archive cache version. Vector rows with a different dimension are skipped rather than mixed. Conversation history has its own lane: cosine recall of 128 history windows, BM25 scoring of every recalled window, RRF rerank, and the top 15 raw windows. It is always current-only and is returned alongside the archive results as `history_results`.
- File, memory, summary, and folder changes bump the default index version. Provider writes bump the `providers` scope, while system prompts and frequent prompts use their own scopes. Ingest-settings changes are read fresh and do not need cache invalidation.
- Memories are a linear timeline. Active rows are searchable; supersession or direct deprecation marks the old row deprecated, stamps provenance, and makes its chunks non-current. The row and its text remain readable through `read_memory` and the chain.
- Summaries are derived views over memories and are indexed as `summary` chunks. Agent-facing summary output must remain visibly compressed, with coverage and source-memory counts.
- `TimelineService` merges memories, summaries, and current-file updates. Sparse reads (the agent tool and the default API) sample up to five anchors per kind and report skipped counts; complete reads (`complete=true`, the human Timeline page) return the whole window with `anchor=None`, `sampled == total`, `skipped=0`, `skips=[]`, and density from `timeline_density`. The cache key includes the mode, and both modes keep the per-kind safety cap and `truncated` flag.
- Provider configuration uses four capability tables (`chat`, `embedding`, `web_search`, `web_fetch`) with one active row each enforced by partial unique indexes. A chat row is an endpoint with an optional `max_output_tokens`, and `anthropic` is admitted beside `deepseek`, `openai-compatible`, and `none`. Keys are Fernet-encrypted and endpoint-owned; a provider-scoped environment key enriches only that provider's row. `AiRuntime` reloads after writes. `ModelAssignmentService` owns the per-account assignment: `app_user` row ids are resolved exactly, with no fallback, and the auxiliary slot inherits the primary only when both auxiliary fields are NULL. A changed slot must pass a 16-token probe; a failure is `422 model_probe_failed` and writes nothing.
- Every file version with a visual gets one tiny WebP thumbnail (long edge 320 px, usually under 12 KiB) in the private `file_thumbnail` table, written in the same transaction as the file row. Images render through Pillow, PDF page 1 through PDFium under the shared `pdfium_lock`, and PPTX/DOCX/XLSX/ODS through the preview the writer embedded; text formats get no row and Office files without a preview get `status='none'`. A render failure is recorded as `failed` and never fails ingestion. Byte-identical content (copy, re-upload, folder copy) reuses an existing thumbnail instead of rendering again. `GET /files/{id}/thumbnail?v=<version>` is `immutable` when `v` matches and revalidates with a strong ETag otherwise. Only the dedicated worker runs `FileThumbnailBackfill` (`APSOR_THUMBNAIL_BACKFILL_ENABLED`); `script/backfill_thumbnails.py` is the one-off equivalent. Bump `GENERATOR_VERSION` in `domain/thumbnail_domain.py` whenever renderer output changes.
- Markdown edits require `expected_version`. A stale value is `409 file_version_conflict`; a changed extension is `422 invalid_path`; non-Markdown content is rejected as `unsupported_file_type`.

## Key files

- `model/file_model.py`, `model/folder_model.py` — version lineage and explicit folder tree.
- `model/chunk_model.py`, `model/ngram_model.py` — unified retrieval storage.
- `model/memory_model.py`, `model/summary_model.py` — timeline, supersession, summaries.
- `model/ingest_job_model.py`, `model/ingest_config_model.py` — durable queue, runtime config, prompt templates.
- `domain/vision_prompt_domain.py` — default prompts, rendering, required-key validation, warnings, mode mapping.
- `domain/spreadsheet_domain.py` — spreadsheet limits, cell formatting, and Markdown table rendering.
- `service/spreadsheet_extractor.py` — calamine extraction, formula fallback, merged cells.
- `service/spreadsheet_guard.py` — pre-parse zip and declared-grid guards for ODS/XLSX.
- `service/file_service.py` — extraction, versioning, Markdown update, move/copy/delete, path reads, re-ingest source.
- `model/file_thumbnail_model.py`, `repository/file_thumbnail_repository.py` — per-version WebP thumbnail rows, reuse by content hash, and clone.
- `domain/thumbnail_domain.py`, `service/thumbnail_renderer.py`, `service/pdfium_lock.py` — thumbnail size/quality rules, the CPU-bound renderer, and the process-wide PDFium lock.
- `service/thumbnail_backfill.py` — worker-only cross-account backfill (ids via maintenance session, work in each owner's `user_session`).
- `service/embedding_backfill.py` — worker-only loop that embeds pending chunks after provider or allowance failures; `service/embedding_backfill_status.py` is the API-side root status and retry nudge.
- `service/ingest_job_service.py` — job enqueue (upload/text/reingest), leases, staging, publication, failure recovery.
- `domain/ingest_progress_domain.py` — thread-safe parse/chunk tracker shared with extraction threads.
- `service/ingest_progress_service.py` — SSE snapshot, Pub/Sub relay, keepalives, and polling fallback.
- `service/ingest_settings_service.py` — runtime settings and the separate vision prompt read/save surface.
- `service/indexer_service.py` — chunk persistence, n-grams, embeddings, retries.
- `service/history_chunk_store.py` — knowledge-side write adapter for conversation-history windows; still routes through `IndexerService`.
- `service/search_service.py` — BM25 + vector recall + RRF + caching, including the separate history lane.
- `service/memory_service.py`, `service/timeline_service.py` — memory lineage and sparse/complete time reads.
- `service/related_memory_service.py` — owner-scoped related memories for a memory or a file: RRF over stored-embedding cosine and top n-gram BM25, plus shared-summary and time-proximity signals. It never calls a provider or spends embedding quota, excludes the supersession chain, and scans non-current memory chunks only when deprecated memories are requested.
- `service/provider_config_service.py` — capability registry, encryption, activation, reindexing.
- `dependencies.py` — composition of all knowledge services, worker factories, provider runtime.
- `service/summary_service.py`, `service/stats_service.py`, `service/ai_service.py` — summaries, dashboard stats, and the AI status/ask facade.
- `service/model_assignment_service.py` — per-account chat endpoint/model assignments and probes.
- `service/provider_error_notice_service.py` / `service/metered_text_generator.py` — provider failure notices and quota-metered text generation.
- `service/cache_keys.py` — owner-scoped cache keys and version scopes.
- `service/health_service.py` — database readiness probe behind `GET /health`.
- `router/` — `file`, `folder`, `tree`, `memory`, `search`, `timeline`, `settings`, `ingest_settings`, `ingest_progress` (SSE, mounted separately), `model_assignment`, `provider_notice`, `ai`, `system`, `health`, and the `tool` facade.
- `domain/` — path validation, chunking, timeline sampling, provider table specs (`provider_config_domain.py`), and resolved provider value objects (`provider_runtime_domain.py`). The signed-hashing embedder is an adapter in `app/infrastructure/embedding/hashing_embedder.py`.
- `exception/domain_error.py` — stable knowledge errors; `exception/handler.py` maps them to HTTP status and codes.

## Conventions

- Every list, search, and retrieval query must explicitly filter `is_current` and `deleted_at` where the model supports it. History is opt-in, never the default.
- Never hard-delete a file or memory to represent supersession or deletion. Soft-delete files and deprecate memories; preserve ids and historical rows.
- Lock the current file row before changing content, location, name, or deletion state. Do not “fix” a historical row by toggling `is_current` directly.
- When replacing a file version, mark the previous current row and its chunks non-current, then publish the replacement atomically. Durable jobs must never expose a partial current file.
- All content writes go through `IndexerService`; do not add a second chunking, n-gram, or embedding path. Keep embedding batch size, retries, and concurrency bounded. Conversation history is no exception: the agent indexer builds fixed 256-character drafts and `HistoryChunkStore` writes them through `IndexerService` with `source_kind='history'`. Never store XML tags in a history chunk's content; the id envelope is applied at retrieval time so BM25 and vectors see raw text only.
- Keep storage and database writes paired. Delete newly written bytes if persistence fails, and delete staged chunks when a job is discarded.
- Treat `ingest_config` as a runtime snapshot. Do not silently mutate existing chunk boundaries or reinterpret persisted embeddings after an embedder change; report/reindex instead. The two vision prompt columns are a separate surface: runtime update/reset must not write them, and they are never versioned.
- Re-ingest must never mutate the current file row or own the source original. Keep `source_kind='reingest'` jobs payload-free, read the shared original through the owner's `FileService`, and publish only through `publish_pending(expected_current_file_id=...)`. Failure, retry, and startup recovery must not delete source bytes.
- Reuse the shared `CacheProtocol` and scope-aware version keys. Do not cache mutable search or registry results without a version in the key.
- Preserve path and extension safety checks, upload/text limits, and stable error codes. Do not bypass `normalize_path` or folder checks in a new route.
- Schema changes need a new Alembic revision and constraint/index updates. Test schema creation does not validate migrations.
- Add behavioral coverage to the matching file under `backend/tests/`; use the public API and deterministic fakes rather than a live database or provider.

## Verification

```bash
cd backend
uv run ruff check app/module/knowledge tests/test_file_library.py tests/test_markdown_update.py tests/test_search.py tests/test_memories.py tests/test_summaries.py tests/test_timeline.py tests/test_versions.py
uv run mypy app
uv run lint-imports
uv run pytest -q tests/test_file_library.py tests/test_markdown_update.py tests/test_search.py
uv run pytest -q tests/test_memories.py tests/test_summaries.py tests/test_timeline.py tests/test_versions.py
```

Run the full backend suite for ingestion, retrieval, or lineage changes. Migration upgrade/downgrade must be checked separately against the development database; never use the live archive.

## Related guides

- [Parent](../../AGENTS.md)
- [Agent slice](../agent/AGENTS.md)
- [Backend tests](../../../tests/AGENTS.md)
