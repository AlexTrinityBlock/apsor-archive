# Configuration

**English** · [繁體中文](zh-TW/configuration.md) · [简体中文](zh-CN/configuration.md)

### Configure providers in the app

The Settings page is the normal way to configure providers, and only the root
account can edit the global registry. It writes to four independent capability
tables, so one capability can never overwrite another:

- **Chat** — `chat_provider_config`: DeepSeek, Anthropic Claude, or any
  OpenAI-compatible chat endpoint. A chat row is an **endpoint** that accounts
  are assigned to; it has an optional `max_output_tokens` cap (256–131,072).
- **Embedding** — `embedding_provider_config`: offline `hashing`, `openai`, or
  `openai-compatible`. Several rows may form one chain, but every active row
  must use the same model and dimension.
- **Web search** — `web_search_provider_config`: Tavily, Exa, or DeepSeek.
  Several rows may be active as one ordered chain.
- **Web fetch** — `web_fetch_provider_config`: Tavily `extract`, Exa
  `contents`, or DeepSeek `fetch`. Web search and web fetch are deliberately
  separate rows, so they can use different providers or different credentials.

Every table stores a zero-based `priority` and a partial unique index on
`priority WHERE is_active`. For embedding, web search, and web fetch, the first
chain row is the primary and the rest are backups; a request advances to the
next row only on a provider or transport failure, and the operation fails only
after every row fails. Chat is different: each account is assigned one exact
chat row, and an agent turn never fails over to another chat row. Embedding
backups must share the primary's model and dimension, since mixing vector
spaces would corrupt the per-owner index. Deleting a row does not reuse its
identity id.

Provider rows are global deployment configuration: only the root account can
list, edit, test, or delete them, and normal users never receive a provider
secret or a global runtime setting. The API never returns a plaintext key: the
browser receives only a hint such as `...14f8`. `APSOR_SECRET_KEY` supplies the
Fernet master key. If it is unset, a `0600` key file is created at
`data/.secret_key` (or `/data/.secret_key` in Docker), so encrypted values
survive restarts. `APSOR_TAVILY_API_KEY` is an optional environment fallback
for both web capabilities. An Exa key can live in the gitignored
`.secrets/exa.env` as `EXA_API_KEY` (or as `APSOR_EXA_API_KEY`); the encrypted
provider row still wins. The same `APSOR_DEEPSEEK_API_KEY` used for chat is the
environment fallback for the DeepSeek web search and web fetch provider, so no
separate web credential is needed. An Anthropic key can live in
`.secrets/anthropic.env` as `ANTHROPIC_API_KEY` (or as
`APSOR_ANTHROPIC_API_KEY`); a database key on the endpoint row still wins.

A chat endpoint owns its key, not the account. Multiple accounts may share one
endpoint, and rotating or clearing the endpoint's key affects every account
assigned to it. A row with no encrypted key may use the provider-scoped
environment key as row enrichment, but there is no per-user key and no
deployment-wide chat fallback: an unassigned account is never rescued by
another active row or by an environment key alone.

Precedence for embedding, web search, and web fetch is: **active database chain
→ environment → built-in default**. For chat, the account assignment selects an
endpoint row by id; the provider-scoped environment key can only complete that
row. The Settings page labels each provider with its source and shows the chain
order. Changing the embedding model does not rewrite existing vectors;
`reindex_required` warns you. Run **Re-embed library** (or
`POST /api/v1/settings/providers/embedding/reindex`) to refresh current chunks.
Vector search skips chunks whose dimension does not match the current embedder.

Provider registry API:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | Four capability groups, masked hints, ordered chain, reindex advice |
| `POST` | `/api/v1/settings/providers/{capability}` | Create one saved provider; optionally append it to the chain |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | Replace one saved provider without reordering the chain |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | Delete one saved provider and close the chain gap |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | Append the row, or pass `priority=0` to make it primary |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/deactivate` | Remove one row from the chain and close the gap |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | Clear the whole chain; embedding/web fall back to environment/default, chat assignments become inactive |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | One small provider request plus latency |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | Re-embed every current chunk with the active provider |

`{capability}` is one of `chat`, `embedding`, `web_search`, or `web_fetch`.
The registry response is cached for 30 seconds under the `providers` cache
scope; every provider write bumps that scope.

When an entire chain fails, the API and worker record one sanitized
`provider_error_notice` row and root sees it on the Accounts page. Notices
deduplicate by capability, operation, and error code inside a 15-minute window;
`count` and `last_seen_at` advance on repeats. The table holds only provider
metadata, never prompts or archive content. Root can list, resolve one, or
resolve all:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/system/provider-notices?status=open\|all&limit=50` | Open notices plus the unresolved count |
| `POST` | `/api/v1/system/provider-notices/{notice_id}/resolve` | Resolve one notice |
| `POST` | `/api/v1/system/provider-notices/resolve-all` | Resolve every open notice |

### Per-account model assignment

Every account has two chat slots. The **primary** slot serves agent chat. The
**auxiliary** slot serves summaries, memory consolidation, ingest titles, tags
and document analysis, extraction, and vision. Root assigns both from
**Accounts → Model**: choose a saved chat endpoint, type the model name and
reasoning effort, set the optional context budget, then press **Test** on each
slot whose connection changed. A normal account reads the same two slots from
**Settings → Model**; that view is read-only.

Model names and effort strings are free text, up to 128 and 32 characters. The
model catalog is advisory, never an allow-list. A known model may add prices, a
tier, and a tokenizer ratio; an unknown model is accepted with `tier=None`, no
routing, no automatic escalation, and `unpriced` cost. The effort hints in the
dialog are provider guidance only: DeepSeek accepts `low | high | max` (default
`high`, with `minimal`→`low`, `medium`/`xhigh`→`high`, and `ultra`→`max`
aliases), Anthropic accepts `low | medium | high | xhigh | max`, and
OpenAI/GPT accepts `none | minimal | low | medium | high | xhigh | max`
depending on the model. The probe is the validation.

The endpoint row owns the Fernet-encrypted key. Multiple accounts may share one
endpoint, and rotating or clearing its key affects every account assigned to it.
There is no per-user key and no global or environment chat fallback: a missing,
inactive, disabled, or keyless endpoint fails closed. The auxiliary slot
inherits the primary endpoint and model only when both auxiliary fields are
`NULL` (the upgrade backfill shape); that inherited work uses the auxiliary
effort, `low` by default. A stored auxiliary row without a model, or a model
without a row, is reported as degraded instead of silently falling back.

Saves are probe-gated. The server tests each slot whose connection fingerprint
(endpoint row, base URL, key ciphertext, model, and effort) changed with one real
16-token generation, and `PUT` re-checks that gate server-side even when the
browser already pressed **Test**. A budget-only change skips the probe. If a
probe fails, the request returns `422 model_probe_failed` and writes nothing.
Deleting an assignment clears both slots and leaves the account unassigned.

The context window and compaction threshold are optional per-account overrides;
a blank value inherits the deployment default from `agent_config`. The context
window is a real outbound input budget, not model metadata. Before each provider
call the agent estimates the request and never raises a local context error:
over budget, it first force-compacts deterministically at 60% of the budget,
then drops page context, then clips tool-result bodies oldest-first at 8,000,
then 2,000, then 500 characters while keeping the `<tool_result>` envelope, and
finally truncates only the outbound copy of the current user message (dropping
its attachments if needed). One `ui.notice` records what the model did not see.
The stored transcript is unchanged. There is no `agent_context_limit_exceeded`
code.

Compaction is always deterministic and never calls a provider. Root can edit its
instruction template in `agent_config`; the template must contain
`{max_output_tokens}` and may use `{max_output_chars}`, `{max_items}`,
`{max_line_chars}`, and `{max_last_user_chars}`. A template that omits the
output bound, uses an unknown placeholder, or contains a stray brace returns
`422 compaction_prompt_invalid` and does not save.

With `model_escalation_enabled` on, the agent may escalate at most once per run,
one catalog tier up, on the same endpoint. It does so after a context-window
rejection that survived one compaction, an output-limit completion that produced
no text after its retry, three consecutive invalid-argument tool calls, an
unusable completion, or a refusal. It never escalates on 5xx, timeout, 401/403,
or quota errors. A `ui.notice` records `reason`, `from_model`, and `to_model`.
An unknown model has no tier, so it never escalates.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/model-assignments` | Every account's stored, effective, and warning fields (root only) |
| `GET` | `/api/v1/model-assignments/me` | The caller's own assignment (every authenticated account) |
| `PUT` | `/api/v1/model-assignments/{user_id}` | Probe changed slots and save both assignments (root only) |
| `DELETE` | `/api/v1/model-assignments/{user_id}` | Clear both assignments (root only) |
| `GET` | `/api/v1/chat-endpoints` | Saved chat endpoints, host name only, never a key or full URL |
| `POST` | `/api/v1/chat-endpoints/{provider_config_id}/probe` | Test one candidate model/effort; writes nothing |
| `GET` | `/api/v1/model-catalog` | Advisory catalog in escalation order; other model strings stay legal |

Stable assignment errors:

| Status | Code | When |
|---|---|---|
| `409` | `model_not_assigned` | The account has no primary endpoint/model |
| `409` | `provider_inactive` | The assigned endpoint is inactive, disabled, or keyless |
| `422` | `invalid_model_assignment` | An endpoint is unusable, or the budget pair is invalid |
| `422` | `model_probe_failed` | A changed slot failed its probe; nothing was written |
| `422` | `compaction_prompt_invalid` | The compaction template omits `{max_output_tokens}` or has an unknown placeholder |

Catalog prices are informational; the existing per-account token quotas remain
the enforcement, and there is no dollar-cost readout. `GET /api/v1/ai/status`
still reports the deployment-global runtime for root diagnostics; it is not the
per-account assignment.

### Web research tools

The agent has two read-only tools for external research:

| Tool | What it does |
|---|---|
| `web_search` | Search the public web with the active `web_search` provider; returns title, URL, an optional score, and a bounded excerpt. |
| `web_fetch` | Fetch one public `http(s)` URL with the active `web_fetch` provider and return one server-defined Markdown page. |

Tavily (`/search` and `/extract`), Exa (`/search` and `/contents`), and
DeepSeek (`/v1/tools/search` and `/v1/tools/fetch`) are the implemented
adapters. The provider seam is a protocol, so another search or fetch API can be
added without changing the tool layer. Search results are cached for 15 minutes
under the `providers` cache scope; provider writes invalidate them. `web_fetch`
rejects non-HTTP(S), credentials in the URL, `localhost`/`.local`/`.internal`,
and private or special-use IP literals.

`web_fetch` caches the complete extracted document once per URL for one hour, so
paging never calls the provider again. A structurally suspicious extraction (a
heading immediately followed by a same-or-higher heading, or a document ending
on a heading) is not cached, so a later page request re-queries the provider
instead of pinning a partial document. The final page footer says
`End of extracted content.` and adds a warning when a heading has no body before
the next heading. Its model-facing arguments are only `url` and `page` (1-based,
default 1). The server hard-wraps every source line
at 800 characters and packs whole lines into pages of up to 12,000 characters
(or the configured `web_fetch_max_chars` when smaller, never below 801), so a
page never exceeds its budget and always contains at least one line. There are no line numbers to count
and no offsets to compute: call `page=1`, then `page=2`, and so on until
`has_more=false`. Each result reports `page`/`total_pages`, `page_chars`,
`total_chars`, `has_more`, `next_page`, and `source_truncated`, and the body ends
with a plain-text footer such as:

```text
[web_fetch: page 1/2. More content: call web_fetch again with page=2.]
```

`next_page` is exact whenever `has_more=true`. Concatenating every page covers
the cached document exactly once, with no gaps or overlaps. The normalized full
document is capped at 2,000,000 characters; beyond that it is cut and
`source_truncated=true`, so the final page footer says the source was truncated.
Both tools return XML carrying `provider`, `retrieved_at`, `cached`, and
`truncated`, and the agent is instructed to cite the URL and retrieval time.

A conversation freezes its tool snapshot when it is created, so an older
conversation keeps its previous `web_fetch` schema. The former `offset`,
`limit`, and `max_chars` arguments are still accepted but hidden from the
model-facing schema; they exist only so conversations frozen on
`archive-tools-v4`/`v5` keep validating. Page mode ignores `max_chars` and
`limit`, and a legacy `offset` simply selects the page that contains that line.

Summary search results and timeline summary events are explicitly marked as
compressed views:

```xml
<source kind="summary" id="12" view="compressed" memory_count="37" ...>
  <compressed_view coverage_start="..." coverage_end="..." source_memory_count="37">
    This is a compressed summary of 37 original memories, not the complete original content.
  </compressed_view>
  ...
</source>
```

The agent sees `view="compressed"`, the coverage window, and the original memory
count in the tool result itself, so it does not treat a summary as a full
transcript.

### Frequently used prompts

The **Frequent prompts** panel on `/settings` edits the shortcuts shown on the
empty `/chat` page. The list is private to the signed-in account: each row has a
title, prompt text, and `sort_order`; the list is capped at 20 rows per account,
ordered by `sort_order` then `id`, and cached for 60 seconds under that account's
`prompts` cache scope. Clicking a shortcut fills the composer with its full
prompt text; it does not send the message. The API is
`GET/POST/PUT/DELETE /api/v1/settings/frequent-prompts`.

### Chat companion

> *We could never travel that far. So we made someone who could, and taught
> them everything we loved.*

The six built-in librarians (Vellum, Atlas, Herbaria, Horologe, Nocturne,
Quill) are figures of ten-thousand-year aeon-porcelain whose minds woke, undesigned,
from the library's human writing; they keep each archive together with one
person, as equals. Their world is written down in
[`backend/app/module/companion/lore/BIBLE.md`](../backend/app/module/companion/lore/BIBLE.md)
with one character bible per librarian under `lore/characters/`, an English
canon (`canon.json`, `GLOSSARY.md`), and complete zh-TW and zh-CN translations
with shared term tables (`lore/zh-*/TERMS.md`).

A small librarian can stand freely beside the chat (no strings or control bar)
and react to the agent: it thinks while the model reasons, searches during `search_knowledge`, reads,
writes, calculates, browses, and presents during the matching tools, and the
agent can also call the read-only `companion_action` tool for an explicit
gesture. Built-in presets ship with the frontend. Each account may also create up
to 20 private custom companions and upload up to 12 images per action (PNG,
JPEG, WebP, or AVIF, at most 8 MB each); the server re-encodes every image as
AVIF (WebP only when the AVIF codec is unavailable) that fits 384x576 and 40 KB
and strips its metadata. The per-account preference stores
the selected companion (`preset:<id>` or `custom:<id>`), whether it is shown, the
motion level (`full`, `reduced`, `off`), its display size (`compact`, `medium`,
`full`; full shows the art at up to 384x576 and only scales down to fit the
window and the free space beside the chat), its opacity mode (`opaque`,
`translucent`, or `auto`, which fades only while it overlaps the page or you
type or scroll), and its normalized position. Each account configures all of
this on its own **Companion** page (`/companion`, in the sidebar's personal
section), which also hosts the story editor and custom companions; old
`/settings#settings-companion` links redirect there. The API is
under `/api/v1/companions` (list, create, update, delete, frame upload, frame
order, frame delete, frame image, and `GET/PATCH /api/v1/companions/preference`).

Each companion also has a story: a persona that becomes its voice in new
conversations (frozen per conversation, in the conversation's language), and
lore, its own memories. Nothing is locked: every memory carries a weight
(everyday, past, or heart) and the librarian decides whether, when, and how much
to share, knowing how long she and the person have known each other. Relevant
memories may ride beside a message or a tool result in a separate block, and she
can look her own memories up with the `recall_my_memories` tool, including what
she and the other librarians said to this person before (each past reply records
who said it). Her memories are never archive evidence or citations;
`search_knowledge` searches only the person's archive. The persona rules treat the user as an equal: the librarian uses
their name or a plain "you", never a title such as Keeper or master. Every
account can edit the persona and lore of any companion per language and reset
to the default (`/api/v1/companions/stories/...`).

### Agent runtime settings

The **Agent runtime** panel on `/settings` (root only) edits the singleton
`agent_config` row (`id=1`). Chat endpoint and model selection are per-account
assignments (see **Per-account model assignment**); this row carries the
parallel-tool and per-result tool budgets, the deployment-default context
budget, and the compaction and escalation controls. All nineteen runtime values are stored in PostgreSQL,
apply to new runs without a restart, and are shared by every account. An
account's own context window and compaction threshold override these deployment
defaults when set. The two chat-image lifetime values are also read by the
background cleanup loop from this row; they are not environment variables.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | Effective config, defaults, source, `updated_at` |
| `PUT` | `/api/v1/agent/settings` | Full replacement; all nineteen fields are required |
| `POST` | `/api/v1/agent/settings/reset` | Persist and return the built-in defaults |

The generated operations are `getAgentSettings`, `updateAgentSettings`, and
`resetAgentSettings`.

The read shape is `{config, defaults, source, updated_at}`, where `source` is
`database` for a stored row or `default` when the API had to create or repair the
row from defaults. `PUT` requires a complete snapshot: omitted fields and extra
fields are rejected.

| Field | Default | Range |
|---|---|---|
| `compaction_threshold_tokens` | 75,000 | 1,000–1,000,000; below the context window |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000; deployment default budget |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `compaction_prompt` | built-in template | 1–20,000 characters; must contain `{max_output_tokens}` |
| `compaction_max_output_tokens` | 2,600 | 256–16,384 |
| `model_escalation_enabled` | `true` | boolean |
| `agent_max_output_tokens` | 64,000 | 256–131,072 |
| `auto_compaction_enabled` | `true` | boolean |
| `parallel_tools_enabled` | `true` | boolean |
| `save_memory_requires_approval` | `true` | boolean; manual approval for `save_memory` |
| `chat_attachment_staged_ttl_hours` | 1 | 1–168; unsent upload grace period |
| `chat_attachment_cleanup_interval_seconds` | 900 | 60–86,400; cleanup sweep interval |
| `max_plot_points` | 10,000 | 100–50,000; data points per rendered figure |
| `max_plot_bytes` | 600,000 | 10,000–2,000,000; serialized figure size |
| `max_plot_nodes` | 100,000 | 1,000–500,000; JSON nodes per figure |

Pydantic and matching PostgreSQL check constraints enforce the ranges and three
cross-field rules: the compaction threshold must stay below the model context
window, the parallel width must not exceed tool calls per turn, and
`max_plot_nodes` must be at least `max_plot_points`. The compaction template also
must render with the known placeholders; literal braces are doubled, and a
missing `{max_output_tokens}` or an unknown placeholder is rejected as
`422 compaction_prompt_invalid` instead of `400 invalid_request`. The plot
budgets apply to `render_plot` for every account. The app's global validation
envelope maps other request validation failures to `400 invalid_request` rather
than 422.

A request loads one immutable runtime snapshot in a short-lived database session.
An active SSE run keeps the snapshot it started with; later runs use changed
settings. The backend contract is described in `backend/README.md`.

### Ingestion runtime

The synchronous `POST /api/v1/files` and `POST /api/v1/files/text` endpoints
remain, but the UI can enqueue work instead. The async routes store the payload
and return `202` with an `IngestJobSchema`:

| Method | Path | Operation |
|---|---|---|
| `POST` | `/api/v1/files/async` | `uploadFileAsync` |
| `POST` | `/api/v1/files/text/async` | `createTextFileAsync` |
| `GET` | `/api/v1/files/ingest-jobs?limit=&offset=` | `listIngestJobs` |
| `GET` | `/api/v1/files/ingest-jobs/{id}` | `getIngestJob` |
| `POST` | `/api/v1/files/ingest-jobs/{id}/retry` | `retryIngestJob` |
| `POST` | `/api/v1/files/{file_id}/reingest` | `reingestFile` |

A job moves through `queued(0)`, `parsing(5)`, `chunking(15–20)`,
`embedding(25–90)`, `summarizing(95)`, and `ready(100)`, or ends as `failed`.
`progress_pct`, `chunks_total`, and `chunks_embedded` are durable, so a reloaded
page can resume the same display. Staged file and chunk rows are published only
when the job is ready; a failed job keeps its error but exposes no partial
current file.

One worker process polls the database every second while idle and claims queued
rows with `SELECT ... FOR UPDATE SKIP LOCKED`. It runs two extraction threads
and at most two in-flight jobs, with global async embedding concurrency of six
and batched progress updates. Stale jobs are requeued after a crash, and
embedding retries are bounded. The API only enqueues jobs, so run the worker
beside it (`make worker` locally, a dedicated service in production). Setting
`APSOR_INGEST_WORKER_ENABLED=true` instead runs the same loops inside the API
process as a single-process development shortcut; it defaults to `false`.

```bash
cd backend
uv run apsor-archive worker
# or
uv run python -m app.worker
# process at most one job, then exit
uv run python -m app.worker --once
```

The standard and Cloudflare Compose stacks run this as a dedicated `worker`
service and set `APSOR_INGEST_WORKER_ENABLED=false` on the API, so exactly one
process owns the queue.

#### RabbitMQ dispatch

The Compose stacks also run `rabbitmq:4-management-alpine` as an optional
low-latency dispatch path for durable ingestion. PostgreSQL `file_ingest_job`
remains the authoritative job ledger: a message carries only `{job_id,
retry_count}`, and the consumer re-reads the row, claims it with
`SELECT ... FOR UPDATE SKIP LOCKED`, and decides from the database status. A
duplicate, late, or lost message can only cost latency; it can never become a
second source of truth.

- The API publishes persistent JSON messages to the durable `apsor.ingest`
  direct exchange with publisher confirms. The publish path is time-boxed at
  one second (`APSOR_RABBITMQ_PUBLISH_TIMEOUT_SECONDS`); a broker failure is
  logged by exception type and swallowed, so the upload still returns `202` and
  the job stays `queued`.
- The worker consumes `apsor.ingest.jobs` with `prefetch_count=1` and manual
  acknowledgements. It acks only after `process_notified_job` returns: a worker
  crash leaves the delivery unacked, RabbitMQ redelivers it, and the job resumes
  or retries from its row.
- `retry` outcomes and unexpected handler failures publish to
  `apsor.ingest.jobs.retry`, a 30-second TTL queue that dead-letters back to the
  main queue. Dispatch retries are capped at 20 so a broken job cannot loop
  forever.
- The container is capped at 384 MB with a 200 MB VM watermark
  (`docker/rabbitmq/rabbitmq.conf`). The management UI stays on the Compose
  network and is not published on the host; the local demo credentials are
  `apsor` / `apsor` and must be changed through
  `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` before any shared deployment.
- Disable dispatch with `APSOR_RABBITMQ_ENABLED=false`. The API then uses the
  no-op notifier and the worker keeps polling PostgreSQL every second, so no job
  is lost. The same polling fallback applies while the broker is down or a
  notifier connection fails.

The **Ingestion runtime** panel on `/settings` (root only) edits the singleton
`ingest_config` row. It is a full replacement, not a patch, and the read body
carries `{config, defaults, source, updated_at}` with a Database/Defaults badge.
The worker may claim jobs across accounts, but every parse, chunk, embedding, and
publish step runs in the job owner's row-level-security context.

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/v1/settings/ingest` | `getIngestSettings` |
| `PUT` | `/api/v1/settings/ingest` | `updateIngestSettings` |
| `POST` | `/api/v1/settings/ingest/reset` | `resetIngestSettings` |

| Field | Default | Range |
|---|---|---|
| `poll_seconds` | 1.0 | 0.25–30 |
| `extract_workers` | 2 | 1–8 |
| `max_inflight_jobs` | 2 | 1–4 |
| `embedding_concurrency` | 6 | 1–32 |
| `chunk_target_chars` | 4,000 | 1,000–20,000 |
| `chunk_overlap_chars` | 500 | 0–5,000; below target |
| `vision_description_language` | `English` | 1–80 characters; free text |

The worker reads a fresh database snapshot each loop and job, so saved worker
changes apply without a restart; a job already running keeps its snapshot.
Environment values seed a fresh install and remain the fallback. Changing chunk
sizes affects only future ingests. `vision_description_language` controls only
the visual description, caption, title, summary, and tags; OCR text and table
cell text stay verbatim in the source language. Changing it applies only to
future ingests, and existing files keep their current extraction. The backend
contract is described in `backend/README.md`.

#### Vision prompts

The two vision system prompts are stored separately from the runtime snapshot,
so `PUT /settings/ingest` and the runtime reset never overwrite them. `NULL`
means the built-in default. Root can read and replace both templates in one
save; the body is the full prompt text, including any `{language}` placeholder.

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/v1/settings/ingest/vision-prompts` | `getIngestVisionPrompts` |
| `PUT` | `/api/v1/settings/ingest/vision-prompts` | `updateIngestVisionPrompts` |

The read body returns the current `config`, built-in `defaults`, `source`,
`updated_at`, `max_chars`, the nine required keys, template SHA-256 values, and
non-blocking `warnings`. Saving rejects an empty or over-32K prompt, control
characters, or a prompt missing any required output key (`422
invalid_vision_prompt`). The response also returns warnings when the prompt
omits `verbatim`, `do not translate`, or GitHub-Flavored Markdown wording.

`POST /api/v1/files/{file_id}/reingest` accepts `{expected_version}` and queues
a forced vision pass for a current image, PDF, DOCX, or PPTX with a stored
original.
The job creates a new file version only after extraction and indexing succeed;
the previous version remains current and readable until then. The original
bytes are shared, never copied or deleted by the job. If the path changes or a
newer upload becomes current first, the job fails with `409
ingest_source_stale` and the newer file stays current.
