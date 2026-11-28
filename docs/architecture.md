# Architecture

**English** · [繁體中文](zh-TW/architecture.md) · [简体中文](zh-CN/architecture.md)

## Stack

| Layer | Choice |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, psycopg 3 |
| Storage | PostgreSQL 17 (`pg_trgm` for path fuzzy search); original bytes in RustFS (default), Cloudflare R2, any S3-compatible bucket, or local disk |
| Cache | Valkey / Redis-compatible, with a memory fallback |
| Retrieval | CJK bigram + Latin token n-grams, BM25, signed hashing vectors, RRF |
| AI | DeepSeek `deepseek-flash`, Anthropic Claude, or any OpenAI-compatible chat endpoint |
| Frontend | React 19, TypeScript, Vite, React Router, React Query, Orval |
| Deploy | Docker Compose with Caddy and Cloudflare Tunnel, or bare metal with `uv` |

## How retrieval works

1. **Normalize** with NFKC and lower-case. Punctuation becomes whitespace.
2. **Index** overlapping CJK bigrams, Latin words, and Latin trigrams. Each chunk
   stores a unique n-gram list with term frequencies.
3. **BM25** scores candidates (`k1=1.2`, `b=0.75`). A union query such as
   `automobile ford` naturally favours chunks that contain both terms.
4. **Vector recall** uses a 384-dimensional signed feature-hashing embedder by
   default, so it works offline. Set `APSOR_EMBEDDING_PROVIDER=openai` and the
   matching base URL/model to use a hosted embedding model instead.
5. **Fuse** with reciprocal rank fusion. Each archive source kind keeps its own
   top `result_number`, so a summary cannot be crowded out by file chunks.
6. **Deduplicate** by chunk id, then hydrate the file, memory, or summary row.
7. **Conversation history** runs a separate flat-index lane. Every user or
   assistant message longer than 256 characters is cut into 256-character
   windows with a 32-character overlap (stride 224). The query embedding takes
   the top 128 windows by cosine similarity; BM25 scores every recalled window;
   reciprocal rank fusion reranks the union and keeps the top 15. History
   windows are always included, regardless of the archive-history switch. Each
   hit carries the stable `agent_entry` id, which the agent expands with
   `history_message`. Deleted conversations are marked non-current and disappear
   from this lane.

If vector recall is unavailable, search still returns BM25 results. An
embedding failure never loses a passage: when the provider is out of credits
(for example OpenAI `insufficient_quota`), rejects the key, is unreachable, or
the account's embedding allowance is spent, every ingestion path (durable
worker jobs, synchronous text, Markdown edits, memories, summaries, and
conversation history) still stores the chunk's text and n-grams, so keyword
search finds it at once, and leaves its vector *pending* (`embedding IS NULL`).
The dedicated worker's `EmbeddingBackfill` loop
(`APSOR_EMBEDDING_BACKFILL_ENABLED`, on by default) fills pending vectors in
automatically:

- Provider failures (billing, quota, authentication, rate limits, outages)
  pause the loop with exponential backoff up to 30 minutes and never count
  against a passage. It resumes on its own after the backoff, immediately when
  the embedding provider configuration changes, or when root presses
  **Retry now** in the system notices after recharging.
- An account whose own embedding allowance is spent is skipped until root raises
  the grant or the period resets; the backfill records usage like any other
  embedding.
- A passage the provider rejects as input (HTTP 400/413/422) is retried alone
  up to five times and then left keyword-only.

Root sees the pending count, the worker state, and the next retry time in the
system notices (`GET /api/v1/system/embedding-backfill`; `POST
/api/v1/system/embedding-backfill/retry`). Only a provider refresh that would
switch model or dimension in the middle of a durable job still fails that job,
so one file never mixes two vector spaces.

### Do I need an embedding model key?

No. The default signed feature-hashing embedder runs offline and gives real
lexical vector recall. BM25 over CJK bigrams handles exact terms and names. If
you want semantic or cross-lingual recall, point the service at an
OpenAI-compatible embedding endpoint:

```bash
mkdir -p .secrets
cat > .secrets/openai.env <<'EOF'
APSOR_EMBEDDING_PROVIDER=openai
APSOR_EMBEDDING_BASE_URL=https://api.openai.com/v1
APSOR_EMBEDDING_MODEL=text-embedding-3-small
APSOR_EMBEDDING_DIMENSION=1536
APSOR_EMBEDDING_API_KEY=sk-...
EOF
chmod 755 .secrets
sudo chgrp 10001 .secrets/openai.env
chmod 640 .secrets/openai.env
```

The Settings page can also store this configuration in the database. After
changing the embedding model, open Settings and run **Re-embed library** (or call
`POST /api/v1/settings/providers/embedding/reindex`) so existing chunks get vectors in
the new dimension. Until then, text search still works and vector search skips
the incompatible chunks.

### What is a signed hashing embedder?

It is a deterministic feature-hashing vectorizer, not a trained neural model.
Each token (a CJK bigram, a Latin word, or a Latin trigram) is hashed with
BLAKE2b into one of 384 buckets. One bit of the digest becomes the sign, so
collisions partially cancel instead of always adding up. The bucket values are
accumulated and the vector is L2-normalized.

```text
token -> BLAKE2b -> bucket 0..383 + sign(+1/-1) -> accumulate -> normalize
```

Consequences:

- **No model download, no GPU, no key.** It runs on the CPU in microseconds per
  chunk and needs only a few kilobytes of RAM per vector.
- **Lexical, not semantic.** `car` and `automobile` are different tokens. BM25
  handles exact terms, but query phrasing matters.
- **Deterministic.** The same text always produces the same vector, which makes
  ingestion and tests reproducible.
- **Exact scan at personal scale.** The current implementation scans up to
  20,000 current vectors and computes cosine in Python. At a larger corpus,
  replace it with pgvector/HNSW or a hosted embedding model; the
  `EmbedderProtocol` boundary stays the same.


## Data model

The schema follows three rules: source metadata lives in its owning table, the
unified chunk table stores only the source key, and every private row carries
exactly one owner.

```text
file ─────────────┐
folder ───────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┤
agent_entry ──────┘  (source_kind = history)
```

The private archive tables below carry `user_id bigint NOT NULL`. The exceptions
are the global config tables (`agent_config`, `ingest_config`,
`system_prompt_section`, and the four provider tables), which are shared
deployment configuration, and the auth tables (`app_user`, `user_session`),
which hold identity rather than archive content.
Parent/child links in private tables use composite `(id, user_id)` foreign keys,
so a row cannot point into another account's lineage. Forced PostgreSQL
row-level security on the `apsor_app` role is the database backstop; request
transactions set `app.user_id` for the duration of one transaction. Auth tables
deliberately stay outside RLS because login and session lookup happen before a
user context exists; global config tables are read-all/root-write.

- `file`: one row per version. `is_current` and `deleted_at` are soft state;
  ids are never reused. File leaves are not duplicated in the folder table:
  their placement is `raw_file_path`. `storage_backend` records `local`, `r2`, or
  `s3` for the original bytes and is null exactly when `storage_key` is null.
- `folder`: explicit folder records (`parent_id`, `path`, `name`, `depth`).
  Empty folders and folder identity survive independently of files. Uniqueness
  is per account: `(user_id, path)`.
- `chunk`: `(source_kind, source_id, chunk_index)` with an optional JSONB vector.
  `source_kind` is `file`, `memory`, `summary`, or `history`; a history chunk's
  `source_id` is the immutable `agent_entry` id and its content is one raw
  256-character window.
- `chunk_ngram`: the inverted index used by BM25.
- `memory`: linear timeline with an auto-generated `title`, `supersedes_ids`,
  `superseded_by_id`, `status=active|deprecated`, and the direct-retirement
  provenance `deprecated_at` / `deprecated_reason`. A deprecated row must have a
  successor or a `deprecated_at` timestamp.
- `memory_summary`: period, source memory ids, themes, generator, and model.
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`: one row per saved
  provider, with an encrypted API key, a safe hint, and the model/base
  URL/dimension. `chat_provider_config` also stores an optional
  `max_output_tokens` and admits `anthropic`, `deepseek`,
  `openai-compatible`, and `none`; a chat row is an endpoint that accounts are
  assigned to. A partial unique index on `is_active` enforces one active row
  per capability. `web_search` and `web_fetch` are independent credentials.
- `app_user`: one row per account. `role` is `root` or `user`; `is_active`,
  `must_change_password`, `disabled_at`, `created_by_user_id`, and the password
  audit timestamps model the account lifecycle. The eight assignment columns are
  `chat_provider_config_id`, `chat_model`, `chat_reasoning_effort`,
  `aux_provider_config_id`, `aux_model`, `aux_reasoning_effort` (not null,
  default `low`), `chat_context_window_tokens`, and
  `chat_compaction_threshold_tokens`. A partial unique index enforces exactly
  one root, and usernames stay globally unique and immutable.
- `user_profile_card`: ordered title/content cards that describe the account; the
  full set is frozen into a new conversation as the `user_profile` section.
- `frequently_used_prompt`: private, account-editable shortcuts for the empty
  chat page, ordered by `sort_order` and capped at 20 rows per account.
- `agent_conversation` / `agent_entry` / `agent_run`: the persistent agent's
  transcript scope, immutable entry log, and per-submission run state.
  `agent_commit_seq` groups entries written in one transaction. Page snapshots
  are `pi.page-context` entries in the same log, not a separate table.
- `agent_approval`: durable pending/approved/rejected/expired human decisions for
  confirmation-required writes, with validated arguments, a safe preview, and
  the loop snapshot used to resume the waiting run.
- `agent_config`: one row (`id=1`) with the validated runtime limits used by the
  agent loop and the settings API, including the compaction template and output
  cap plus the escalation switch.
- `saved_question`: the account's Q&A library. `question` is user-authored;
  `answer`, `citations`, `conversation_id`, and the run status/error fields are
  written only by an ask. `conversation_id` uses `ON DELETE SET NULL`, and
  `last_asked_at` records the most recent attempt.
- `file_ingest_job`: the durable intake queue. It stores the source kind, path,
  payload key and backend, status/stage, `progress_pct`, chunk counts, bounded
  error fields, and attempt/timestamps. A path can have only one active job per
  account. The job points at its staged file, clears that link on failure, and
  the file and chunks become current only when the job publishes them.
- `file_thumbnail`: one tiny WebP per file version, keyed by `file_id`, with
  `status` (`ready`, `none`, or `failed`), pixel size, SHA-256, generator
  version, and attempt count. It cascades with its file.
- `companion` / `companion_frame` / `companion_preference`: an account's custom
  chat companions, their encoded AVIF (or WebP) frames per action with position,
  size, and SHA-256, and the account's companion choice, visibility, motion
  level, and position.
- `companion_story` / `companion_lore_fragment` / `companion_bond`: an
  account's per-locale persona and lore overrides for a companion, their
  fragments, and the run and conversation counts plus when they first met.
- `ingest_config`: one row (`id=1`) with the validated worker poll, extraction,
  in-flight, embedding, and chunk-size settings. It is not a chunk source; the
  queue references the file that is eventually published.

Original bytes are not stored in PostgreSQL. They live on local disk, in the private R2
bucket, or in an S3-compatible bucket (RustFS by default), selected per file by
`storage_backend`; the extracted chunks
and their n-grams remain in PostgreSQL.

Code, comments, and documentation are written in English, which is canonical.
The interface and this README also ship complete Traditional and Simplified
Chinese translations that are updated together with the English source.
