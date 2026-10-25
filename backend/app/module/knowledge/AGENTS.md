# Knowledge Module — Agent Guide

The knowledge slice owns the archive itself: versioned files, the folder tree, extracted text and chunks, embeddings, hybrid search, memories and supersession, periodic summaries, the sparse timeline, durable ingestion, and provider configuration.

## Purpose

Keep file lineage, search visibility, and memory history consistent across synchronous API calls, background ingestion, and retrieval. A write is not complete until current rows, chunks, embeddings, and cache invalidation agree.

## Architecture

- `FileModel` is one version row, not one path. When a new upload or Markdown update is published over an existing path, it inserts a new row, points `supersedes_file_id` at the old row, and marks the old row non-current. A partial unique index permits one current, non-deleted row per `raw_file_path`.
- Historical file rows remain readable by id, but mutations require a current row. `update_markdown_content`, move, copy, and delete all go through `_require_current_file_for_update`, which locks the row with `get_current_for_update` (`SELECT ... FOR UPDATE`). A historical or deleted id returns `404 file_not_found`.
- A move changes only `raw_file_path` and `file_name`, preserving id, version, chunks, embeddings, storage key, and links. A copy creates a new current row at version 1, clones stored originals when present, rebuilds chunks/embeddings, and does not copy lineage or supersession.
- `FolderModel` is an explicit tree so empty folders and folder identity are real. File leaves are derived from `file.raw_file_path`. Folder creation is idempotent and creates missing ancestors; a path occupied by the other node kind is `409 tree_path_conflict`.
- `LocalFileStorage` writes opaque relative keys under the configured data directory and refuses path escapes. Original bytes and database rows must be cleaned up together when an ingestion or copy fails.
- `ChunkModel` is one polymorphic search table for `file`, `memory`, and `summary` sources. It stores content, char/token counts, JSONB embeddings, embedding model, and `is_current`; `chunk_ngram` stores term frequencies for BM25. Source metadata stays in the owning table.
- `IndexerService` is the single chunk/embedding pipeline. It splits text, writes chunks and n-grams, embeds in bounded batches with bounded retry, and can stage rows (`is_current=False`) until a durable job publishes them. Strict worker mode surfaces embedding failure; legacy callers may retain text-only chunks.
- Chunk boundaries are stored per file. The singleton `ingest_config` row supplies future chunk sizes; changing `chunk_target_chars` or `chunk_overlap_chars` affects only future ingests, and existing files keep their boundaries until re-ingested.
- Durable ingestion uses `file_ingest_job` with `queued → parsing → chunking → embedding → summarizing → ready`, or `failed`. The worker claims with `SELECT ... FOR UPDATE SKIP LOCKED`, owns staged rows, publishes only on success, discards them on failure, and requeues stale leases after a crash.
- `search_service.py` runs BM25 over CJK bigrams and Latin terms, optional vector recall by cosine similarity, and reciprocal-rank fusion. Results are selected per source kind, de-duplicated by chunk, hydrated, and cached under the archive cache version. Vector rows with a different dimension are skipped rather than mixed.
- File, memory, summary, and folder changes bump the default index version. Provider writes bump the `providers` scope, while system prompts and frequent prompts use their own scopes. Ingest-settings changes are read fresh and do not need cache invalidation.
- Memories are a linear timeline. Active rows are searchable; supersession or direct deprecation marks the old row deprecated, stamps provenance, and makes its chunks non-current. The row and its text remain readable through `read_memory` and the chain.
- Summaries are derived views over memories and are indexed as `summary` chunks. Agent-facing summary output must remain visibly compressed, with coverage and source-memory counts.
- `TimelineService` merges memories, summaries, and current-file updates, samples up to five anchors per kind, returns density, and reports skipped/truncated counts honestly.
- Provider configuration uses four capability tables (`chat`, `embedding`, `web_search`, `web_fetch`) with one active row each enforced by partial unique indexes. Keys are Fernet-encrypted; `AiRuntime` resolves active row → environment → default and reloads after writes.
- Markdown edits require `expected_version`. A stale value is `409 file_version_conflict`; a changed extension is `422 invalid_path`; non-Markdown content is rejected as `unsupported_file_type`.

## Key files

- `model/file_model.py`, `model/folder_model.py` — version lineage and explicit folder tree.
- `model/chunk_model.py`, `model/ngram_model.py` — unified retrieval storage.
- `model/memory_model.py`, `model/summary_model.py` — timeline, supersession, summaries.
- `model/ingest_job_model.py`, `model/ingest_config_model.py` — durable queue and runtime config.
- `service/file_service.py` — extraction, versioning, Markdown update, move/copy/delete, path reads.
- `service/ingest_job_service.py` — job enqueue, leases, staging, publication, failure recovery.
- `service/indexer_service.py` — chunk persistence, n-grams, embeddings, retries.
- `service/search_service.py` — BM25 + vector recall + RRF + caching.
- `service/memory_service.py`, `service/timeline_service.py` — memory lineage and sparse time reads.
- `service/provider_config_service.py` — capability registry, encryption, activation, reindexing.
- `dependencies.py` — composition of all knowledge services, worker factories, provider runtime.
- `router/` — files, folders, paths, memories, summaries, search, timeline, settings, tool facade.
- `domain/` — path validation, chunking, hashing embedder, timeline sampling, provider specs.
- `exception/domain_error.py` — stable knowledge errors and their handler mappings.

## Conventions

- Every list, search, and retrieval query must explicitly filter `is_current` and `deleted_at` where the model supports it. History is opt-in, never the default.
- Never hard-delete a file or memory to represent supersession or deletion. Soft-delete files and deprecate memories; preserve ids and historical rows.
- Lock the current file row before changing content, location, name, or deletion state. Do not “fix” a historical row by toggling `is_current` directly.
- When replacing a file version, mark the previous current row and its chunks non-current, then publish the replacement atomically. Durable jobs must never expose a partial current file.
- All content writes go through `IndexerService`; do not add a second chunking, n-gram, or embedding path. Keep embedding batch size, retries, and concurrency bounded.
- Keep storage and database writes paired. Delete newly written bytes if persistence fails, and delete staged chunks when a job is discarded.
- Treat `ingest_config` as a runtime snapshot. Do not silently mutate existing chunk boundaries or reinterpret persisted embeddings after an embedder change; report/reindex instead.
- Reuse the shared `CacheProtocol` and scope-aware version keys. Do not cache mutable search or registry results without a version in the key.
- Preserve path and extension safety checks, upload/text limits, and stable error codes. Do not bypass `normalize_path` or folder checks in a new route.
- Schema changes need a new Alembic revision and constraint/index updates. Test schema creation does not validate migrations.
- Add behavioral coverage to the matching file under `backend/tests/`; use the public API and deterministic fakes rather than a live database or provider.

## Verification

```bash
cd backend
uv run ruff check app/module/knowledge tests/test_file_library.py tests/test_markdown_update.py tests/test_search.py tests/test_memories.py tests/test_summaries.py tests/test_timeline.py tests/test_versions.py
uv run mypy app
uv run pytest -q tests/test_file_library.py tests/test_markdown_update.py tests/test_search.py
uv run pytest -q tests/test_memories.py tests/test_summaries.py tests/test_timeline.py tests/test_versions.py
```

Run the full backend suite for ingestion, retrieval, or lineage changes. Migration upgrade/downgrade must be checked separately against the development database; never use the live archive.

## Related guides

- [Parent](../../AGENTS.md)
- [Agent slice](../agent/AGENTS.md)
- [Backend tests](../../../tests/AGENTS.md)
